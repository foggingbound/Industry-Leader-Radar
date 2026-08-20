from __future__ import annotations

import json
import math
import os
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 财经接口必须直连。Windows 的系统代理即使没有出现在环境变量中，
# requests 仍可能自动继承；失效代理会导致 ProxyError。
for proxy_name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(proxy_name, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import requests

_requests_session_init = requests.sessions.Session.__init__


def _direct_session_init(self, *args, **kwargs):
    _requests_session_init(self, *args, **kwargs)
    self.trust_env = False


requests.sessions.Session.__init__ = _direct_session_init

import akshare as ak
import pandas as pd


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("LEADER_RADAR_PORT", "18765"))
CACHE_SECONDS = 300
STALE_REFRESH_SECONDS = 600
CACHE_FILE = ROOT / "live_data_cache.json"
ENTRY_FILE = "龙头雷达-60题材增强独立版-v3-文案替换版.html"
_cache: dict[str, dict] = {}
_lock = threading.Lock()
_upstream_lock = threading.Lock()
_refreshing: set[str] = set()
_refresh_errors: dict[str, tuple[float, str]] = {}
_last_upstream_call = 0.0


def load_cache():
    global _cache
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            _cache = raw
    except Exception:
        _cache = {}


def save_cache():
    temporary = CACHE_FILE.with_suffix(".tmp")
    with _lock:
        content = json.dumps(_cache, ensure_ascii=False, indent=2)
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(CACHE_FILE)


def pace_upstream():
    global _last_upstream_call
    delay = 1.2 - (time.time() - _last_upstream_call)
    if delay > 0:
        time.sleep(delay)
    _last_upstream_call = time.time()


load_cache()


def direct_get(url: str, *, params: dict | None = None, timeout: int = 10):
    last_error = None
    for attempt in range(3):
        try:
            with _upstream_lock:
                pace_upstream()
                response = requests.get(
                    url,
                    params=params,
                    timeout=timeout,
                    proxies={"http": None, "https": None},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
                        "Accept": "application/json,text/plain,*/*",
                        "Connection": "close",
                    },
                )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2.0 * (attempt + 1))
    raise last_error


def resolve_symbol(name: str, code: str) -> tuple[str, str, str]:
    symbol = code.split(".")[0] if code and code != "离线模拟" else ""
    suffix = code.split(".")[-1].upper() if "." in code else ""
    if symbol.isdigit() and len(symbol) in (5, 6):
        market = (
            "HK"
            if suffix == "HK"
            else "BJ"
            if suffix == "BJ"
            else "SH"
            if suffix == "SH" or symbol.startswith(("5", "6", "9"))
            else "SZ"
        )
        return symbol, market, name
    data = direct_get(
        "https://searchapi.eastmoney.com/api/suggest/get",
        params={"input": name, "type": "14", "token": "D43BF722C8E33BDC906FB84D85E326E8"},
    ).json()
    items = ((data.get("QuotationCodeTable") or {}).get("Data") or [])
    for item in items:
        found_code = str(item.get("Code") or "")
        if len(found_code) == 6 and found_code.isdigit():
            market = "SH" if str(item.get("MktNum")) == "1" or found_code.startswith(("5", "6", "9")) else "SZ"
            return found_code, market, str(item.get("Name") or name)
    raise ValueError(f"未找到 {name} 的股票代码")


def realtime_quote(name: str, code: str) -> dict:
    symbol, market, resolved_name = resolve_symbol(name, code)
    if market == "HK":
        return tencent_quote(name, code)
    secid = f"{1 if market == 'SH' else 0}.{symbol}"
    payload = direct_get(
        "https://push2.eastmoney.com/api/qt/stock/get",
        params={
            "secid": secid,
            "invt": "2",
            "fltt": "2",
            "fields": "f43,f57,f58,f60,f170,f162,f167",
        },
    ).json()
    row = payload.get("data") or {}
    current = clean_number(row.get("f43"))
    if current is None:
        raise ValueError(f"未取得 {resolved_name} 的实时价格")
    return {
        "代码": symbol,
        "名称": row.get("f58") or resolved_name,
        "最新价": current,
        "涨跌幅": clean_number(row.get("f170")),
        "昨收": clean_number(row.get("f60")),
        "市盈率TTM": clean_number(row.get("f162")),
        "市净率": clean_number(row.get("f167")),
        "market": market,
    }


def tencent_quote(name: str, code: str) -> dict:
    symbol, market, resolved_name = resolve_symbol(name, code)
    if market == "HK":
        quote_symbol = "r_hk" + symbol.zfill(5)
    else:
        quote_symbol = ("sh" if market == "SH" else "sz") + symbol
    response = direct_get(
        "https://qt.gtimg.cn/q=" + quote_symbol,
        timeout=10,
    )
    response.encoding = "gbk"
    text = response.text
    if '="' not in text:
        raise ValueError(f"未取得 {resolved_name} 的腾讯行情")
    fields = text.split('="', 1)[1].rsplit('"', 1)[0].split("~")
    current = clean_number(fields[3] if len(fields) > 3 else None)
    previous_close = clean_number(fields[4] if len(fields) > 4 else None)
    change_pct = clean_number(fields[32] if len(fields) > 32 else None)
    if current is None:
        raise ValueError(f"未取得 {resolved_name} 的腾讯实时价格")
    return {
        "代码": symbol,
        "名称": fields[1] if len(fields) > 1 and fields[1] else resolved_name,
        "最新价": current,
        "涨跌幅": change_pct,
        "昨收": previous_close,
        "市盈率TTM": clean_number(fields[39] if len(fields) > 39 else None),
        "市净率": clean_number(fields[46] if len(fields) > 46 else None),
        "market": market,
    }


def resilient_quote(name: str, code: str) -> tuple[dict, str]:
    errors = []
    for provider, fetcher in (("东方财富", realtime_quote), ("腾讯行情", tencent_quote)):
        try:
            return fetcher(name, code), provider
        except Exception as exc:
            errors.append(f"{provider}：{exc}")
    raise ValueError("；".join(errors))


def clean_number(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def first_number(row: dict, *keys: str):
    for key in keys:
        value = clean_number(row.get(key))
        if value is not None:
            return value
    return None


def first_matching_number(row: dict, *keywords: str):
    for key, raw_value in row.items():
        label = str(key).replace(" ", "")
        if any(word in label for word in keywords):
            value = clean_number(raw_value)
            if value is not None:
                return value
    return None


def latest_finance(market_code: str, symbol: str) -> tuple[dict, str]:
    errors = []
    try:
        with _upstream_lock:
            pace_upstream()
            frame = ak.stock_financial_analysis_indicator_em(symbol=market_code, indicator="按报告期")
        if not frame.empty:
            return frame.iloc[0].to_dict(), "东方财富财务数据"
    except Exception as exc:
        errors.append(f"东方财富财务接口：{exc}")
    try:
        with _upstream_lock:
            pace_upstream()
            frame = ak.stock_financial_analysis_indicator(symbol=symbol, start_year=str(time.localtime().tm_year - 2))
        if not frame.empty:
            return frame.iloc[-1].to_dict(), "新浪财经财务数据"
    except Exception as exc:
        errors.append(f"新浪财经财务接口：{exc}")
    raise ValueError("；".join(errors) or "未找到最新财务指标")


def fetch_stock_data(name: str, code: str, previous: dict | None = None) -> dict:
    quote, quote_source = resilient_quote(name, code)
    symbol = str(quote["代码"]).zfill(6)
    market_code = f"{symbol}.{quote['market']}"
    current = first_number(quote, "最新价")
    change_pct = first_number(quote, "涨跌幅")
    previous_close = first_number(quote, "昨收")

    latest_close = current
    try:
        end = time.strftime("%Y%m%d")
        with _upstream_lock:
            pace_upstream()
            history = ak.stock_zh_a_hist(
                symbol=symbol, period="daily", start_date="20250101", end_date=end, adjust=""
            )
        if not history.empty:
            latest_close = clean_number(history.iloc[-1].get("收盘")) or current
    except Exception:
        pass

    finance_error = None
    try:
        if quote["market"] == "HK":
            with _upstream_lock:
                pace_upstream()
                frame = ak.stock_hk_financial_indicator_em(symbol=symbol)
            report = frame.iloc[0].to_dict() if not frame.empty else {}
            finance_source = "AKShare 港股核心财务指标"
        elif quote["market"] == "BJ":
            report, finance_source = {}, "北交所财务指标暂使用缓存/空值"
        else:
            report, finance_source = latest_finance(market_code, symbol)
    except Exception as exc:
        finance_error = str(exc)
        report, finance_source = {}, "财务数据暂时不可用"

    eps = first_number(report, "EPSJB", "BASIC_EPS", "基本每股收益", "每股收益") or first_matching_number(report, "每股收益", "基本每股收益")
    bps = first_number(report, "BPS", "每股净资产") or first_matching_number(report, "每股净资产")
    profit_growth = first_number(
        report, "PARENT_NETPROFIT_YOY", "NETPROFIT_YOY", "SJLTZ", "归母净利润同比增长"
    )
    net_margin = first_number(report, "XSJLL", "NET_PROFIT_RATIO", "销售净利率", "净利润率") or first_matching_number(report, "销售净利率", "净利润率")
    asset_turnover = first_number(report, "TOAZZL", "TOTAL_ASSET_TURNOVER", "总资产周转率") or first_matching_number(report, "总资产周转率")
    roe = first_number(report, "ROEJQ", "ROE_AVG", "净资产收益率") or first_matching_number(report, "净资产收益率", "股东权益回报率")
    roa = first_number(report, "ZZCJLL", "ROA", "总资产净利率", "总资产收益率") or first_matching_number(report, "总资产净利率", "总资产收益率", "总资产报酬率")
    leverage = roe / roa if roe is not None and roa not in (None, 0) else None

    pe = current / eps if current is not None and eps not in (None, 0) else first_number(quote, "市盈率TTM")
    pb = current / bps if current is not None and bps not in (None, 0) else first_number(quote, "市净率")
    peg = pe / profit_growth if pe is not None and profit_growth not in (None, 0) and profit_growth > 0 else None

    report_date = str(report.get("REPORT_DATE") or report.get("报告期") or "")[:10]
    old_fundamental = (previous or {}).get("fundamental") or {}
    old_valuation = (previous or {}).get("valuation") or {}
    result = {
        "name": str(quote.get("名称", name)),
        "code": market_code,
        "quote": {
            "current": current,
            "changePct": change_pct,
            "close": latest_close,
            "previousClose": previous_close,
        },
        "valuation": {
            "pe": pe if pe is not None else old_valuation.get("pe"),
            "pb": pb if pb is not None else old_valuation.get("pb"),
            "peg": peg if peg is not None else old_valuation.get("peg"),
        },
        "fundamental": {
            "netMargin": net_margin if net_margin is not None else old_fundamental.get("netMargin"),
            "assetTurnover": asset_turnover if asset_turnover is not None else old_fundamental.get("assetTurnover"),
            "financialLeverage": leverage if leverage is not None else old_fundamental.get("financialLeverage"),
            "reportDate": report_date or old_fundamental.get("reportDate", ""),
        },
        "source": f"Codex 当前配置：{quote_source} + {finance_source}" + (f"（{finance_error}）" if finance_error else ""),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    return result


def refresh_cache(cache_key: str, name: str, code: str):
    try:
        with _lock:
            previous = ((_cache.get(cache_key) or {}).get("data") or {})
        result = fetch_stock_data(name, code, previous)
        with _lock:
            _cache[cache_key] = {"savedAt": time.time(), "data": result}
            _refresh_errors.pop(cache_key, None)
        save_cache()
    except Exception as exc:
        with _lock:
            _refresh_errors[cache_key] = (time.time(), str(exc))
        print(f"后台刷新失败 [{name}]：{exc}")
    finally:
        with _lock:
            _refreshing.discard(cache_key)


def stock_data(name: str, code: str) -> dict:
    cache_key = f"{name}|{code}"
    with _lock:
        cached = _cache.get(cache_key)
    if cached and isinstance(cached.get("data"), dict):
        age = time.time() - float(cached.get("savedAt") or 0)
        data = dict(cached["data"])
        if age > STALE_REFRESH_SECONDS:
            with _lock:
                should_refresh = cache_key not in _refreshing
                if should_refresh:
                    _refreshing.add(cache_key)
            if should_refresh:
                threading.Thread(
                    target=refresh_cache,
                    args=(cache_key, name, code),
                    daemon=True,
                ).start()
            data["source"] = f"{data.get('source', '在线数据')}（使用上次成功缓存，后台刷新中）"
        return data

    result = fetch_stock_data(name, code)
    with _lock:
        _cache[cache_key] = {"savedAt": time.time(), "data": result}
    save_cache()
    return result


def queued_stock_data(name: str, code: str) -> tuple[str, dict | str | None]:
    cache_key = f"{name}|{code}"
    with _lock:
        cached = _cache.get(cache_key)
        refreshing = cache_key in _refreshing
        last_error = _refresh_errors.get(cache_key)

    if cached and isinstance(cached.get("data"), dict):
        return "ready", stock_data(name, code)

    if refreshing:
        return "pending", None

    if last_error and time.time() - last_error[0] < 15:
        return "error", last_error[1]

    with _lock:
        if cache_key not in _refreshing:
            _refreshing.add(cache_key)
            should_start = True
        else:
            should_start = False
    if should_start:
        threading.Thread(
            target=refresh_cache,
            args=(cache_key, name, code),
            daemon=True,
        ).start()
    return "pending", None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("", "/", "/index.html"):
            self.path = "/" + ENTRY_FILE
            return super().do_GET()
        if parsed.path != "/api/stock":
            return super().do_GET()
        params = parse_qs(parsed.query)
        name = (params.get("name") or [""])[0].strip()
        code = (params.get("code") or [""])[0].strip()
        state, value = queued_stock_data(name, code)
        if state == "ready":
            payload, status = {"ok": True, "data": value}, 200
        elif state == "pending":
            payload, status = {"ok": False, "pending": True}, 202
        else:
            payload, status = {"ok": False, "error": value}, 502
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass


if __name__ == "__main__":
    address = f"http://{HOST}:{PORT}/"
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"龙头雷达在线版：{address}")
    print("浏览器将自动打开；使用期间请勿关闭本窗口。")
    if os.environ.get("LEADER_RADAR_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(address)).start()
    server.serve_forever()
