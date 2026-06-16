#!/bin/bash
# 🔥 AI热点日报爬虫 — 快速运行脚本
# 用法: bash run.sh [-v] [--no-proxy] [--stats]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

mamba run -n ai_crawler python main.py "$@"
