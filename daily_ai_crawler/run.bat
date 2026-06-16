@echo off
REM 🔥 AI热点日报爬虫 — 快速运行脚本 (Windows)
REM 用法: run.bat [-v] [--no-proxy] [--stats]

cd /d "%~dp0"
mamba run -n ai_crawler python main.py %*
