@echo off
cd /d "%~dp0"
set "LEADER_RADAR_PORT=18765"
set "NO_PROXY=*"
set "no_proxy=*"
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
"D:\python\python.exe" live_data_server.py
if errorlevel 1 pause
