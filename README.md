## Industry-Leader-Radar

全题材龙头雷达是一款面向产业研究与市场观察的本地网页应用，覆盖 60 多个市场题材与产业赛道。项目将题材分类、产业链关系、代表性公司资料和实时行情集中在一个可交互界面中，帮助用户快速了解热门赛道及其核心企业。

> 本项目仅用于信息展示、学习与研究，不构成任何投资建议。市场有风险，投资需谨慎。

## 主要功能

- 覆盖 60 多个题材及产业赛道
- 展示题材逻辑、产业链结构和代表性公司
- 支持公司搜索、题材筛选与详情查看
- 联网获取股票实时价格、涨跌幅及基础市场数据
- 内置本地公司代码映射和题材数据
- 行情结果本地缓存，降低重复请求频率
- 无需数据库，启动后通过浏览器直接使用

## 技术结构

- **前端：** 单文件 HTML、CSS 和 JavaScript
- **本地服务：** Python `ThreadingHTTPServer`
- **数据处理：** pandas、AKShare
- **网络请求：** Requests
- **本地数据：** CSV、JSON

## 环境要求

- Python 3.10 或更高版本
- Windows 10/11（推荐）
- 可正常访问相关公开财经数据接口的网络环境
- Chrome、Edge 或其他现代浏览器

## 快速开始

### 1. 获取项目

```bash
git clone https://github.com/你的用户名/Industry-Leader-Radar.git
cd Industry-Leader-Radar
```

也可以在 GitHub 仓库页面选择 **Code → Download ZIP**，解压后进入项目目录。

### 2. 安装依赖

建议先创建虚拟环境：

```bash
python -m venv .venv
```

Windows PowerShell 激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装运行依赖：

```bash
pip install requests akshare pandas
```

### 3. 配置可选环境变量

如需使用东方财富股票搜索接口，请设置搜索接口 Token：

```powershell
$env:EASTMONEY_SUGGEST_TOKEN="你的Token"
```

已有公司代码映射的数据通常可以直接查询，该变量主要用于名称到股票代码的补充解析。请勿将 Token 写入源码或提交到 GitHub。

其他可用变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LEADER_RADAR_PORT` | `18765` | 本地服务端口 |
| `LEADER_RADAR_NO_BROWSER` | 未设置 | 设为 `1` 时不自动打开浏览器 |
| `EASTMONEY_SUGGEST_TOKEN` | 空 | 股票代码搜索接口 Token |

### 4. 启动应用

推荐在项目目录中运行：

```bash
python live_data_server.py
```

启动成功后，浏览器会自动打开：

```text
http://127.0.0.1:18765/
```

使用期间请保持 Python 服务窗口运行。按 `Ctrl+C` 可停止服务。

> 仓库中的 `启动在线版.bat` 使用了原开发环境的 Python 路径。如果你的 Python 安装位置不同，请修改批处理文件中的路径，或直接使用上面的 Python 命令启动。

## 项目结构

```text
Industry-Leader-Radar/
├── README.md
├── live_data_server.py                 # 本地服务与行情接口
├── company_codes_map.json              # 公司与证券代码映射
├── 龙头雷达-全部赛道龙头信息.csv       # 题材及龙头公司数据
├── 龙头雷达-60题材增强独立版-v3-文案替换版.html
│                                         # 网页应用入口
└── 启动在线版.bat                       # Windows 快速启动脚本
```

运行时生成的 `live_data_cache.json` 以及 `build/`、`dist/`、`__pycache__/` 等目录已通过 `.gitignore` 排除，不会提交到仓库。

## 数据与缓存

前端通过本地 `/api/stock` 接口请求行情数据。服务会从公开财经数据源获取信息，并将结果缓存到本地：

- 常规缓存有效期为 5 分钟
- 数据更新在后台执行，避免长时间阻塞页面
- 上游接口异常时，页面会显示相应错误信息
- 不同数据源可能存在延迟、缺失或口径差异

请合理控制访问频率，并遵守相关数据源的使用规则。

## GitHub 部署说明

本项目不是纯静态网页，实时行情依赖 `live_data_server.py`。因此：

- GitHub 可以用于托管和版本管理源码
- GitHub Pages 只能展示静态文件，无法运行 Python 行情服务
- 如需公网部署完整功能，应选择支持 Python 常驻进程的平台或服务器
- 当前服务默认仅监听 `127.0.0.1`，适合本机使用；公网部署前需要补充访问控制、反向代理、HTTPS、日志和安全策略

## 常见问题

### 页面可以打开，但实时行情加载失败

确认 Python 服务仍在运行，并检查网络是否能够访问上游财经接口。某些公司还可能需要正确的证券代码映射或 `EASTMONEY_SUGGEST_TOKEN`。

### 端口 `18765` 被占用

可以临时指定其他端口：

```powershell
$env:LEADER_RADAR_PORT="18766"
python live_data_server.py
```

然后访问 `http://127.0.0.1:18766/`。

### 为什么不能直接双击 HTML 使用联网功能

实时行情由本地 Python 接口提供。直接打开 HTML 文件只能加载静态内容，无法正常调用 `/api/stock`，因此需要先启动 `live_data_server.py`。

## 安全提示

- 不要向仓库提交 API Token、账号密码、Cookie 或其他敏感信息
- 不要直接将当前开发服务器暴露到公网
- 公网部署前应增加身份验证、请求限流和输入校验
- 使用第三方数据前，请确认并遵守其服务条款

## 贡献

欢迎通过 Issue 提交问题或建议，也可以通过 Pull Request 改进题材数据、交互体验、兼容性和文档。提交代码前，请确认没有包含个人数据、缓存文件或访问凭据。

## 免责声明

本项目展示的数据可能存在延迟、遗漏或错误，维护者不保证其完整性、准确性和实时性。项目内容不构成证券分析、投资咨询、买卖建议或收益承诺。任何基于本项目内容作出的决策及其后果均由使用者自行承担。
