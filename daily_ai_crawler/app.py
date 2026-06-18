#!/usr/bin/env python3
"""AI热点日报 — 桌面应用 (Flask + 前端 UI)"""

import os
import sys
import json
import glob
import datetime
import threading
import subprocess
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, Response

# ── 兼容 PyInstaller 打包 ─────────────────
_FROZEN = getattr(sys, 'frozen', False)
if _FROZEN:
    _EXE_DIR = os.path.dirname(sys.executable)      # exe 所在目录（可写文件放这里）
    _DATA_DIR = sys._MEIPASS                         # 嵌入数据解压目录（只读文件）
else:
    _EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = _EXE_DIR

os.chdir(_EXE_DIR)

def _data_path(filename):
    """数据文件路径: exe内嵌 → _MEIPASS, 开发 → 项目目录"""
    return os.path.join(_DATA_DIR, filename)

def _user_path(filename):
    """用户文件路径: 始终在exe目录下（可读写）"""
    return os.path.join(_EXE_DIR, filename)

# 覆盖 config 中的路径
import config
config.BASE_DIR = _EXE_DIR
config.REPORTS_DIR = _user_path("reports")
config.DB_FILE = _user_path("crawler.db")
config.SOURCES_FILE = _data_path("sources.yaml")

# lamda_members: 内嵌只读文件
import processors.lamda_matcher as lm
lm._MEMBERS_FILE = _data_path("lamda_members.json")

from config import BASE_DIR, REPORTS_DIR, DB_FILE

app = Flask(__name__)

# ── 确保目录存在 ──────────────────────────
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── 爬虫状态 ──────────────────────────────
_crawl_status = {"running": False, "log": [], "start_time": None}


# ═══════════════════════════════════════════
# API
# ═══════════════════════════════════════════

@app.route("/api/reports")
def list_reports():
    """获取所有历史报告列表"""
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "*.md")), reverse=True)
    reports = []
    for f in files:
        name = os.path.basename(f)
        date_str = name[:10]
        size = os.path.getsize(f)
        # 读取标题
        title = date_str
        try:
            with open(f, "r", encoding="utf-8") as fp:
                first_line = fp.readline().strip("# \n")
                if first_line:
                    title = first_line[:50]
        except Exception:
            pass
        reports.append({
            "date": date_str,
            "filename": name,
            "title": title,
            "size": size,
            "path": f.replace("\\", "/"),
        })
    return jsonify(reports)


@app.route("/api/reports/<date_str>")
def get_report(date_str):
    """获取某日报告内容"""
    filename = f"{date_str}_AI_Hotspot_Report.md"
    filepath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        # 尝试模糊匹配
        matches = glob.glob(os.path.join(REPORTS_DIR, f"{date_str}*.md"))
        if matches:
            filepath = matches[0]
        else:
            return jsonify({"error": "Report not found"}), 404
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"content": content, "date": date_str, "filename": os.path.basename(filepath)})


@app.route("/api/reports/<date_str>", methods=["PUT"])
def save_report(date_str):
    """保存编辑后的报告"""
    data = request.get_json()
    content = data.get("content", "")
    filename = data.get("filename", f"{date_str}_AI_Hotspot_Report.md")
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"ok": True})


@app.route("/api/crawl", methods=["POST"])
def start_crawl():
    """启动一次爬取"""
    global _crawl_status
    if _crawl_status["running"]:
        return jsonify({"error": "Crawler already running"}), 409

    _crawl_status = {"running": True, "log": [], "start_time": datetime.datetime.now().isoformat()}
    threading.Thread(target=_run_crawl, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/crawl/status")
def crawl_status():
    """获取爬取状态 (SSE)"""
    return jsonify(_crawl_status)


@app.route("/api/stats")
def stats():
    """获取数据库统计"""
    import sqlite3
    stats_data = {
        "reports": len(glob.glob(os.path.join(REPORTS_DIR, "*.md"))),
        "history": 0,
        "sources": [],
    }
    if os.path.exists(DB_FILE):
        db = sqlite3.connect(DB_FILE)
        db.row_factory = sqlite3.Row
        try:
            cnt = db.execute("SELECT COUNT(*) as c FROM history").fetchone()
            stats_data["history"] = cnt["c"] if cnt else 0
            srcs = db.execute(
                "SELECT source_name, success_rate, total_fetches FROM source_stats ORDER BY success_rate DESC LIMIT 10"
            ).fetchall()
            stats_data["sources"] = [dict(s) for s in srcs]
        except Exception:
            pass
        db.close()
    return jsonify(stats_data)


# ═══════════════════════════════════════════
# 配置 API
# ═══════════════════════════════════════════

CONFIG_PATH = _user_path("config.local.yaml")
CONFIG_EXAMPLE = _data_path("config.local.yaml.example")

@app.route("/api/config")
def get_config():
    """读取当前配置（脱敏）"""
    cfg = {"github_token": "", "deepseek_api_key": "", "proxy": "", "use_proxy": False, "exists": False}
    if os.path.exists(CONFIG_PATH):
        import yaml as _yaml
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = _yaml.safe_load(f) or {}
            cfg["has_github_token"] = bool(data.get("github_token"))
            cfg["has_deepseek_key"] = bool(data.get("deepseek_api_key"))
            cfg["proxy"] = data.get("proxy", "")
            cfg["use_proxy"] = data.get("use_proxy", False)
            cfg["exists"] = True
        except Exception:
            pass
    return jsonify(cfg)


@app.route("/api/config", methods=["PUT"])
def save_config():
    """保存配置（不覆盖已脱敏的token）"""
    data = request.get_json()
    existing = {}
    if os.path.exists(CONFIG_PATH):
        import yaml as _yaml
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = _yaml.safe_load(f) or {}
        except Exception:
            pass

    # 仅更新非脱敏字段
    for key in ["github_token", "deepseek_api_key", "proxy"]:
        val = data.get(key)
        if isinstance(val, str) and val and "***" not in val:
            if key == "proxy" and val.isdigit():
                val = f"http://127.0.0.1:{val}"
            existing[key] = val
    # use_proxy 是布尔值，单独处理
    if "use_proxy" in data:
        existing["use_proxy"] = bool(data["use_proxy"])

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("# 本地配置 (通过应用界面生成)\n")
        for key in ["github_token", "deepseek_api_key", "proxy", "use_proxy"]:
            f.write(f"{key}: {json.dumps(existing.get(key, ''), ensure_ascii=False)}\n")

    # 更新运行时配置
    config.GITHUB_TOKEN = existing.get("github_token", "")
    config.DEEPSEEK_API_KEY = existing.get("deepseek_api_key", "")
    if existing.get("proxy") and existing.get("use_proxy"):
        config.PROXY_URL = existing["proxy"]
        config.USE_PROXY = True
        config.PROXIES = {"http": config.PROXY_URL, "https": config.PROXY_URL}
    else:
        config.USE_PROXY = False
        config.PROXIES = None

    return jsonify({"ok": True})


def _mask(s: str) -> str:
    if not s or len(s) < 8:
        return s or ""
    return s[:4] + "***" + s[-4:]


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    os._exit(0)


# ═══════════════════════════════════════════
# 爬虫执行
# ═══════════════════════════════════════════

def _run_crawl():
    """直接在进程内调用爬虫（兼容 exe 打包和开发模式）"""
    global _crawl_status
    import asyncio, io, time
    log_buffer = io.StringIO()

    class _LogCapture:
        def write(self, s):
            log_buffer.write(s)
            _crawl_status["log"] = log_buffer.getvalue().split("\n")[-40:]
        def flush(self):
            pass

    try:
        import main as main_module
        crawler = main_module.AIHotspotCrawler(verbose=True)
        # 临时重定向 stdout 来捕获日志
        old_stdout = sys.stdout
        sys.stdout = _LogCapture()
        try:
            asyncio.run(crawler.run())
            _crawl_status["success"] = True
        finally:
            sys.stdout = old_stdout
            crawler.db.close()
    except Exception as e:
        _crawl_status["success"] = False
        import traceback
        _crawl_status["log"].append(f"❌ {e}")
        _crawl_status["log"].append(traceback.format_exc()[-200:])
    _crawl_status["running"] = False


# ═══════════════════════════════════════════
# 前端页面
# ═══════════════════════════════════════════

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 热点日报 · Deep Space Observatory</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🛰️</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Noto+Sans+SC:wght@300;400;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --void: #000008;
  --space: #020518;
  --nebula: #0a0d24;
  --cyan: #00e5ff;
  --cyan-dim: #008099;
  --cyan-glow: rgba(0,229,255,.15);
  --amber: #ff6d00;
  --amber-dim: #994200;
  --amber-glow: rgba(255,109,0,.12);
  --white: #e0e8f0;
  --white-dim: #6b7280;
  --white-faint: #374151;
  --glass: rgba(10,13,36,.75);
  --glass-border: rgba(0,229,255,.1);
  --radius: 2px;
  --transition: .28s cubic-bezier(.4,0,.2,1);
}

* { margin:0; padding:0; box-sizing:border-box; }

body {
  font-family: 'Space Mono', 'Noto Sans SC', monospace;
  background: var(--void);
  color: var(--white);
  height:100vh; display:flex; overflow:hidden;
  -webkit-font-smoothing:antialiased;
}

/* ── Cosmic Particle Field ───────────── */
#particles {
  position:fixed; inset:0; z-index:0; pointer-events:none;
  overflow:hidden;
}
.star {
  position:absolute; border-radius:50%;
  background:var(--white);
  animation: drift linear infinite;
}
@keyframes drift {
  0% { transform:translateY(0) translateX(0); opacity:0; }
  10% { opacity:1; }
  90% { opacity:1; }
  100% { transform:translateY(-100vh) translateX(40px); opacity:0; }
}
.nebula-glow {
  position:fixed; border-radius:50%; filter:blur(160px);
  pointer-events:none; z-index:0; opacity:.25;
}
.nebula-glow.top-right {
  width:600px; height:600px;
  background:radial-gradient(circle, var(--cyan) 0%, transparent 70%);
  top:-200px; right:-200px;
}
.nebula-glow.bottom-left {
  width:500px; height:500px;
  background:radial-gradient(circle, var(--amber) 0%, transparent 70%);
  bottom:-200px; left:-150px;
}
.scanlines {
  position:fixed; inset:0; z-index:999; pointer-events:none;
  background:repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,.03) 2px, rgba(0,0,0,.03) 4px);
  opacity:.4;
}

/* ── Sidebar ────────────────────────── */
#sidebar {
  width:290px; min-width:290px;
  background:var(--glass);
  backdrop-filter:blur(24px);
  -webkit-backdrop-filter:blur(24px);
  border-right:1px solid var(--glass-border);
  display:flex; flex-direction:column; overflow:hidden;
  z-index:10; position:relative;
}
.sidebar-header {
  padding:28px 24px 18px;
  border-bottom:1px solid var(--glass-border);
  position:relative;
}
.sidebar-header::after {
  content:''; position:absolute; bottom:-1px; left:24px; right:24px;
  height:1px; background:linear-gradient(90deg, transparent, var(--cyan-dim), transparent);
}
.sidebar-header .brand {
  font-size:20px; font-weight:700; letter-spacing:3px; text-transform:uppercase;
  background:linear-gradient(135deg, var(--cyan) 20%, #84ffff 60%, var(--cyan));
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  background-clip:text;
  text-shadow:0 0 60px var(--cyan-glow);
}
.sidebar-header .freq {
  font-size:10px; color:var(--white-dim); letter-spacing:4px;
  text-transform:uppercase; margin-top:4px;
}
.sidebar-header .freq .blink {
  display:inline-block; width:8px; height:8px; border-radius:50%;
  background:var(--cyan); margin-right:6px;
  animation:blink 1.5s ease-in-out infinite;
  box-shadow:0 0 8px var(--cyan), 0 0 20px var(--cyan);
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

#report-list {
  flex:1; overflow-y:auto; padding:8px 10px 80px;
}
#report-list::-webkit-scrollbar { width:3px; }
#report-list::-webkit-scrollbar-thumb { background:var(--white-faint); }

.report-item {
  padding:14px 16px; margin:2px 0; cursor:pointer;
  transition:all var(--transition);
  border:1px solid transparent;
  position:relative;
  border-radius:var(--radius);
}
.report-item::before {
  content:''; position:absolute; inset:0; left:0; width:2px;
  background:transparent; transition:background var(--transition);
}
.report-item:hover { background:rgba(0,229,255,.03); }
.report-item.active { background:var(--cyan-glow); border-color:rgba(0,229,255,.15); }
.report-item.active::before { background:var(--cyan); box-shadow:0 0 12px var(--cyan); }
.report-item .r-freq {
  font-size:10px; color:var(--white-dim); letter-spacing:2px;
  display:flex; align-items:center; gap:8px;
}
.report-item .r-freq .pulse {
  width:4px; height:4px; border-radius:50%; background:var(--white-dim);
  transition:all var(--transition);
}
.report-item.active .r-freq .pulse {
  background:var(--cyan); box-shadow:0 0 6px var(--cyan);
}
.report-item .r-title {
  font-size:12px; margin-top:4px; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis;
  color:var(--white-dim); letter-spacing:.5px;
  transition:color var(--transition);
}
.report-item.active .r-title { color:var(--white); }

.sidebar-footer {
  position:absolute; bottom:0; left:0; right:0;
  padding:16px 18px;
  background:linear-gradient(0deg, var(--space) 60%, transparent);
  z-index:2;
}
#btn-crawl {
  width:100%; padding:14px; border:1px solid var(--amber-dim);
  border-radius:var(--radius);
  background:linear-gradient(135deg, rgba(255,109,0,.1), rgba(255,109,0,.05));
  color:var(--amber); font-family:inherit; font-size:13px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; cursor:pointer;
  transition:all var(--transition);
  position:relative; overflow:hidden;
}
#btn-crawl::after {
  content:''; position:absolute; inset:0;
  background:linear-gradient(135deg, transparent 40%, rgba(255,109,0,.1));
}
#btn-crawl:hover {
  border-color:var(--amber);
  box-shadow:0 0 30px var(--amber-glow), inset 0 0 30px var(--amber-glow);
  text-shadow:0 0 20px var(--amber);
}
#btn-crawl:disabled {
  opacity:.5; cursor:not-allowed;
  animation:beacon 2s ease-in-out infinite;
}
@keyframes beacon {
  0%,100% { box-shadow:0 0 10px var(--amber-glow); }
  50% { box-shadow:0 0 40px var(--amber-glow), 0 0 80px rgba(255,109,0,.2); }
}
.sidebar-footer .status-text {
  font-size:10px; color:var(--white-dim); text-align:center;
  margin-top:8px; letter-spacing:2px;
}

/* ── Main ───────────────────────────── */
#main {
  flex:1; display:flex; flex-direction:column; overflow:hidden;
  background:var(--void);
  position:relative; z-index:5;
}
#toolbar {
  padding:14px 28px;
  border-bottom:1px solid var(--glass-border);
  display:flex; align-items:center; gap:16px;
  background:var(--glass);
  backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);
}
#toolbar .doc-title {
  flex:1; font-family:inherit; font-size:14px; font-weight:700;
  color:var(--white); letter-spacing:2px; text-transform:uppercase;
}
#view-mode {
  padding:8px 16px; border:1px solid var(--white-faint);
  border-radius:var(--radius); background:transparent;
  font-family:inherit; font-size:11px; color:var(--white-dim);
  cursor:pointer; outline:none; letter-spacing:1px;
  transition:border-color var(--transition);
}
#view-mode:focus { border-color:var(--cyan); }
.btn-save {
  padding:8px 20px; border:1px solid var(--cyan-dim);
  border-radius:var(--radius); background:transparent;
  color:var(--cyan); cursor:pointer;
  font-family:inherit; font-size:11px; font-weight:700;
  letter-spacing:2px; text-transform:uppercase;
  transition:all var(--transition);
}
.btn-save:hover {
  background:var(--cyan-glow);
  box-shadow:0 0 20px var(--cyan-glow);
}
.btn-settings {
  padding:8px 12px; border:1px solid var(--white-faint);
  border-radius:var(--radius); background:transparent;
  color:var(--white-dim); cursor:pointer;
  font-size:16px; transition:all var(--transition);
  line-height:1;
}
.btn-settings:hover { border-color:var(--amber); color:var(--amber); }

/* ── Settings Modal ──────────────────── */
.modal-overlay {
  position:fixed; inset:0; z-index:200;
  background:rgba(0,0,8,.85);
  backdrop-filter:blur(8px);
  display:none; align-items:center; justify-content:center;
}
.modal-overlay.show { display:flex; }
.modal {
  width:520px; max-height:90vh; overflow-y:auto;
  background:var(--glass);
  backdrop-filter:blur(24px);
  border:1px solid var(--glass-border);
  border-radius:4px;
  padding:36px;
  box-shadow:0 0 80px rgba(0,0,0,.6), 0 0 20px rgba(0,229,255,.1);
  animation:transmissionIn .35s cubic-bezier(.16,1,.3,1);
}
.modal h2 {
  font-size:20px; font-weight:700; letter-spacing:3px;
  color:var(--cyan); margin-bottom:28px; text-transform:uppercase;
}
.modal .form-group {
  margin-bottom:20px;
}
.modal label {
  display:block; font-size:10px; letter-spacing:2px;
  color:var(--white-dim); margin-bottom:6px; text-transform:uppercase;
}
.modal input[type="text"], .modal input[type="password"] {
  width:100%; padding:10px 14px;
  border:1px solid var(--white-faint); border-radius:var(--radius);
  background:rgba(0,0,0,.3); color:var(--white);
  font-family:'Space Mono', monospace; font-size:12px;
  outline:none; letter-spacing:.5px;
  transition:border-color var(--transition);
}
.modal input:focus { border-color:var(--cyan); }
.modal .hint {
  font-size:10px; color:var(--white-dim); margin-top:4px; letter-spacing:.5px;
}
.modal .hint a { color:var(--cyan-dim); }
.modal .checkbox-row {
  display:flex; align-items:center; gap:10px; margin:20px 0;
}
.modal .checkbox-row input[type="checkbox"] {
  width:16px; height:16px; accent-color:var(--cyan);
}
.modal .btn-row {
  display:flex; gap:12px; margin-top:28px;
}
.modal .btn-row button {
  flex:1; padding:12px; border:1px solid var(--white-faint);
  border-radius:var(--radius); background:transparent;
  font-family:inherit; font-size:12px; letter-spacing:2px;
  cursor:pointer; transition:all var(--transition); text-transform:uppercase;
}
.modal .btn-row .btn-primary {
  border-color:var(--cyan); color:var(--cyan); font-weight:700;
}
.modal .btn-row .btn-primary:hover {
  background:var(--cyan-glow); box-shadow:0 0 20px var(--cyan-glow);
}
.modal .btn-row .btn-secondary { color:var(--white-dim); }
.modal .btn-row .btn-secondary:hover { border-color:var(--white-dim); color:var(--white); }
.modal .status-msg {
  font-size:10px; letter-spacing:1px; margin-top:12px; text-align:center;
}
.modal .status-msg.ok { color:#00c853; }
.modal .status-msg.err { color:#ff1744; }

#editor-area { flex:1; display:flex; overflow:hidden; }
#editor {
  flex:1; padding:28px 32px;
  background:rgba(2,5,24,.6);
  color:var(--white); border:none;
  border-right:1px solid var(--glass-border);
  font-family:'Space Mono', 'Noto Sans SC', monospace;
  font-size:12px; line-height:1.9; resize:none; outline:none;
  tab-size:2; letter-spacing:.3px;
}
#editor::placeholder { color:var(--white-faint); font-style:italic; }
#editor:focus { background:rgba(2,5,24,.8); }

#preview {
  flex:1; padding:28px 36px; overflow-y:auto; line-height:1.9;
  font-size:14px; color:var(--white);
  background:rgba(0,0,8,.3);
  position:relative;
}
#preview h1 {
  font-size:26px; font-weight:700; margin-bottom:6px; letter-spacing:2px;
  background:linear-gradient(135deg, var(--cyan), #84ffff);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}
#preview h2 {
  font-size:18px; font-weight:700; margin:28px 0 10px;
  color:var(--amber); letter-spacing:2px; text-transform:uppercase;
  padding-bottom:6px;
  border-bottom:1px solid rgba(255,109,0,.2);
}
#preview h3 { font-size:14px; font-weight:700; margin:16px 0 6px; color:var(--cyan); letter-spacing:1px; }
#preview table {
  border-collapse:collapse; width:100%; margin:12px 0;
  font-size:11px; letter-spacing:.3px;
}
#preview th, #preview td {
  border:1px solid rgba(0,229,255,.08); padding:7px 12px; text-align:left;
}
#preview th {
  background:rgba(0,229,255,.06);
  color:var(--cyan); font-weight:700; font-size:10px; letter-spacing:2px;
  text-transform:uppercase;
}
#preview tr:hover td { background:rgba(0,229,255,.02); }
#preview tr:nth-child(even) td { background:rgba(255,255,255,.01); }
#preview a {
  color:var(--cyan); text-decoration:none;
  border-bottom:1px solid transparent;
  transition:border-color var(--transition);
}
#preview a:hover { border-bottom-color:var(--cyan); }
#preview blockquote {
  border-left:2px solid var(--amber-dim); padding:6px 16px; margin:8px 0;
  color:var(--white-dim); font-style:italic;
  background:rgba(255,109,0,.03);
}
#preview code {
  background:rgba(0,229,255,.06); padding:2px 8px; border-radius:2px;
  font-family:inherit; font-size:11px; color:var(--cyan);
}
#preview hr { border:none; border-top:1px solid var(--glass-border); margin:24px 0; }
#preview strong { color:var(--amber); }
#preview::-webkit-scrollbar { width:3px; }
#preview::-webkit-scrollbar-thumb { background:var(--white-faint); }

/* ── Welcome ─────────────────────────── */
.welcome-hero {
  display:flex; flex-direction:column; align-items:center;
  justify-content:center; height:100%; gap:16px;
}
.welcome-hero h1 {
  font-size:52px; font-weight:700; letter-spacing:8px; text-transform:uppercase;
  background:linear-gradient(135deg, var(--cyan) 30%, #84ffff 60%, var(--cyan));
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
  text-shadow:0 0 80px var(--cyan-glow);
  animation:titlePulse 4s ease-in-out infinite;
}
@keyframes titlePulse {
  0%,100% { filter:brightness(1); }
  50% { filter:brightness(1.3); }
}
.welcome-hero .tagline {
  font-size:12px; color:var(--white-dim); letter-spacing:4px;
  text-transform:uppercase;
}
.welcome-hero .shortcuts {
  margin-top:40px; display:flex; gap:20px;
}
.welcome-hero .shortcut {
  padding:8px 18px; border:1px solid var(--white-faint);
  font-size:10px; color:var(--white-dim); letter-spacing:2px;
  font-family:inherit;
}
.welcome-hero .shortcut kbd {
  color:var(--cyan); font-family:inherit; font-weight:700;
}

/* ── Empty State ──────────────────────── */
.empty-state {
  display:flex; flex-direction:column; align-items:center;
  justify-content:center; height:100%; gap:12px;
  color:var(--white-dim);
}
.empty-state .icon { font-size:48px; opacity:.3; }

/* ── Log Overlay ──────────────────────── */
#log-overlay {
  position:fixed; bottom:20px; right:20px; z-index:100;
  width:440px; max-height:340px;
  background:rgba(2,5,24,.95);
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border:1px solid var(--glass-border);
  box-shadow:0 0 60px rgba(0,0,0,.6), 0 0 10px var(--cyan-glow);
  display:none; flex-direction:column;
  overflow:hidden;
  animation:transmissionIn .4s cubic-bezier(.16,1,.3,1);
}
@keyframes transmissionIn {
  from { opacity:0; transform:translateY(16px) scale(.98); }
  to { opacity:1; transform:translateY(0) scale(1); }
}
#log-overlay.show { display:flex; }
.log-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 18px;
  border-bottom:1px solid var(--glass-border);
  background:rgba(0,229,255,.03);
}
.log-header .log-title {
  font-family:inherit; font-size:10px; letter-spacing:3px;
  text-transform:uppercase; color:var(--cyan);
  display:flex; align-items:center; gap:10px;
}
.log-header .spinner {
  width:14px; height:14px; border:2px solid rgba(0,229,255,.15);
  border-top-color:var(--cyan); border-radius:50%;
  animation:spin .7s linear infinite;
  box-shadow:0 0 10px var(--cyan-glow);
}
@keyframes spin { to { transform:rotate(360deg); } }
.btn-close {
  width:24px; height:24px; border:1px solid rgba(255,255,255,.08);
  border-radius:50%; background:transparent; color:var(--white-dim);
  cursor:pointer; font-size:14px; display:flex;
  align-items:center; justify-content:center;
  transition:all var(--transition); font-family:inherit; line-height:1;
}
.btn-close:hover { border-color:var(--cyan); color:var(--cyan); box-shadow:0 0 12px var(--cyan-glow); }
.log-body {
  flex:1; overflow-y:auto; padding:12px 18px;
  font-family:'Space Mono', monospace; font-size:10px;
  line-height:1.8; letter-spacing:.3px;
}
.log-body .line { white-space:pre-wrap; margin:1px 0; padding:2px 0; border-bottom:1px solid rgba(255,255,255,.015); }
.log-body .line.ok { color:#00c853; }
.log-body .line.warn { color:var(--amber); }
.log-body .line.err { color:#ff1744; }
.log-body .line.info { color:var(--white-dim); }
.log-body::-webkit-scrollbar { width:2px; }
.log-body::-webkit-scrollbar-thumb { background:rgba(0,229,255,.1); }
</style>
</head>
<body>

<!-- Cosmic Background -->
<div id="particles"></div>
<div class="nebula-glow top-right"></div>
<div class="nebula-glow bottom-left"></div>
<div class="scanlines"></div>

<!-- Sidebar -->
<div id="sidebar">
  <div class="sidebar-header">
    <div class="brand">AI OBSERVATORY</div>
    <div class="freq"><span class="blink"></span> SIGNAL INTELLIGENCE</div>
  </div>
  <div id="report-list"></div>
  <div class="sidebar-footer">
    <button id="btn-crawl" onclick="startCrawl()">▶ TRANSMIT</button>
    <p class="status-text" id="status-text">STANDBY</p>
  </div>
</div>

<!-- Main -->
<div id="main">
  <div id="toolbar">
    <span class="doc-title" id="current-title">DEEP SPACE OBSERVATORY</span>
    <select id="view-mode" onchange="setViewMode(this.value)">
      <option value="split">SPLIT VIEW</option>
      <option value="edit">RAW SIGNAL</option>
      <option value="preview">DECODED</option>
    </select>
    <button class="btn-save" onclick="saveReport()">SAVE</button>
    <button class="btn-settings" onclick="openSettings()" title="设置">⚙</button>
  </div>
  <div id="editor-area">
    <textarea id="editor" placeholder="SELECT A REPORT FROM THE LEFT PANEL TO BEGIN DECODING..."
              oninput="onEditorChange()" onkeydown="onEditorKey(event)"></textarea>
    <div id="preview">
      <div class="welcome-hero">
        <h1>AI OBSERVATORY</h1>
        <p class="tagline">Deep Space Signal Intelligence · Daily AI Frontier Briefing</p>
        <div class="shortcuts">
          <div class="shortcut"><kbd>CTRL+S</kbd> SAVE</div>
          <div class="shortcut"><kbd>CLICK</kbd> SELECT REPORT</div>
          <div class="shortcut"><kbd>TRANSMIT</kbd> FETCH SIGNALS</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Transmission Log -->
<div id="log-overlay">
  <div class="log-header">
    <span class="log-title"><span class="spinner" id="log-spinner"></span> TRANSMISSION LOG</span>
    <button class="btn-close" onclick="hideLogOverlay()" title="CLOSE CHANNEL">×</button>
  </div>
  <div class="log-body" id="log-body"></div>
</div>

<!-- Settings Modal -->
<div class="modal-overlay" id="settings-overlay">
  <div class="modal">
    <h2>GROUND STATION CONFIG</h2>
    <p style="font-size:10px;color:var(--white-dim);letter-spacing:1px;margin:-20px 0 24px;text-transform:uppercase">
      所有配置保存在 config.local.yaml · 留空则使用默认值
    </p>
    <div class="form-group">
      <label>GitHub Token <span style="color:var(--white-faint)">(可选，提升API速率)</span></label>
      <input type="password" id="cfg-github" placeholder="ghp_... 留空使用匿名限额 (60次/小时)">
      <div class="hint"><a href="https://github.com/settings/tokens" target="_blank">获取 Token →</a> 勾选 public_repo 即可</div>
    </div>
    <div class="form-group">
      <label>DeepSeek API Key <span style="color:var(--white-faint)">(可选，用于双语翻译)</span></label>
      <input type="password" id="cfg-deepseek" placeholder="sk-... 留空则跳过翻译">
      <div class="hint"><a href="https://platform.deepseek.com" target="_blank">获取 Key →</a> 不填则报告不翻译</div>
    </div>
    <div class="form-group">
      <label>代理端口 <span style="color:var(--white-faint)">(中国大陆用户，自动补全 http://127.0.0.1:)</span></label>
      <input type="text" id="cfg-proxy" placeholder="如 10101，留空直连">
    </div>
    <div class="checkbox-row">
      <input type="checkbox" id="cfg-use-proxy">
      <label style="margin:0;display:inline">启用代理</label>
    </div>
     <div class="btn-row">
      <button class="btn-primary" onclick="saveSettings()">SAVE & APPLY</button>
      <button class="btn-secondary" onclick="closeSettings()">CANCEL</button>
    </div>
    <div class="status-msg" id="settings-msg"></div>
  </div>
</div>

<script>
// ── Particle Field ──
(function(){
  const c = document.getElementById('particles');
  for(let i=0; i<80; i++){
    const s = document.createElement('div');
    s.className = 'star';
    const size = Math.random()*2 + .5;
    s.style.cssText = `
      width:${size}px; height:${size}px;
      left:${Math.random()*100}%;
      top:${Math.random()*100}%;
      animation-duration:${Math.random()*30+20}s;
      animation-delay:${Math.random()*30}s;
      opacity:${Math.random()*.6+.1};
    `;
    c.appendChild(s);
  }
})();

// ── State ──
let currentDate=null, currentFilename=null, originalContent="", pollTimer=null;

marked.setOptions({breaks:true,gfm:true});
loadReports();

async function loadReports(){
  const res = await fetch("/api/reports");
  const reports = await res.json();
  const list = document.getElementById("report-list");
  if(!reports.length){
    list.innerHTML='<div class="empty-state"><div class="icon">&#x1F6F0;</div><p>NO SIGNALS DETECTED</p><p style="font-size:10px;color:var(--white-dim)">INITIATE TRANSMISSION TO BEGIN</p></div>';
    return;
  }
  list.innerHTML = reports.map(r=>'<div class="report-item'+(currentDate===r.date?' active':'')+'" onclick="openReport(\''+r.date+'\')"><div class="r-freq"><span class="pulse"></span>FREQ.'+r.date.replace(/-/g,'.')+'</div><div class="r-title">'+r.title+'</div></div>').join('');
}

async function openReport(date){
  const res = await fetch("/api/reports/"+date);
  const data = await res.json();
  if(data.error) return;
  currentDate = date; currentFilename = data.filename; originalContent = data.content;
  document.getElementById("editor").value = data.content;
  document.getElementById("current-title").textContent = '◆ '+data.filename;
  renderPreview(data.content);
  loadReports();
}

function onEditorChange(){ renderPreview(document.getElementById("editor").value); }
function onEditorKey(e){ if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();saveReport();} }
function renderPreview(md){ document.getElementById("preview").innerHTML = marked.parse(md||''); }
function setViewMode(mode){
  const ed=document.getElementById("editor"), pv=document.getElementById("preview");
  if(mode==="split"){ed.style.display="";pv.style.display="";ed.style.flex="1";pv.style.flex="1";}
  else if(mode==="edit"){ed.style.display="";pv.style.display="none";ed.style.flex="1";}
  else{ed.style.display="none";pv.style.display="";pv.style.flex="1";}
}

async function saveReport(){
  if(!currentDate) return;
  const content = document.getElementById("editor").value;
  await fetch("/api/reports/"+currentDate,{
    method:"PUT",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({content,filename:currentFilename})
  });
  originalContent = content;
  const st = document.getElementById("status-text");
  st.textContent = "SAVED "+new Date().toLocaleTimeString();
  setTimeout(()=>{if(st.textContent.includes("SAVED"))st.textContent="STANDBY";},2000);
}

async function startCrawl(){
  const btn = document.getElementById("btn-crawl");
  if(btn.disabled) return;
  btn.disabled = true; btn.textContent = "TRANSMITTING...";
  showLogOverlay(); document.getElementById("log-spinner").style.display="";
  await fetch("/api/crawl",{method:"POST"});
  pollTimer = setInterval(pollCrawlStatus, 1500);
}
async function pollCrawlStatus(){
  const res = await fetch("/api/crawl/status");
  const s = await res.json();
  if(!s.running){clearInterval(pollTimer);document.getElementById("log-spinner").style.display="none";}
  updateLogBody(s.log||[]);
  const btn=document.getElementById("btn-crawl"), st=document.getElementById("status-text");
  if(!s.running){
    btn.disabled=false; btn.textContent="▶ TRANSMIT";
    st.textContent = s.success ? "RECEIVED" : "TRANSMISSION FAILED";
    loadReports();
    const first = document.querySelector("#report-list .report-item");
    if(first) first.click();
  }
}
function showLogOverlay(){
  document.getElementById("log-overlay").classList.add("show");
  document.getElementById("log-body").innerHTML="";
}
function hideLogOverlay(){
  document.getElementById("log-overlay").classList.remove("show");
}
function updateLogBody(lines){
  const el = document.getElementById("log-body");
  el.innerHTML = lines.map(l=>{
    let cls="info";
    if(l.includes("✅")) cls="ok";
    else if(l.includes("⚠️")||l.includes("超时")) cls="warn";
    else if(l.includes("❌")||l.includes("出错")) cls="err";
    return '<div class="line '+cls+'">'+l+'</div>';
  }).join("");
  el.scrollTop = el.scrollHeight;
}

// ── Settings ──
async function openSettings() {
  document.getElementById("settings-overlay").classList.add("show");
  document.getElementById("settings-msg").textContent = "";
  const res = await fetch("/api/config");
  const cfg = await res.json();
  const ghEl = document.getElementById("cfg-github");
  const dsEl = document.getElementById("cfg-deepseek");
  ghEl.value = ""; dsEl.value = "";
  ghEl.placeholder = cfg.has_github_token ? "已配置 · 留空保持不变" : "ghp_... 留空使用匿名限额";
  dsEl.placeholder = cfg.has_deepseek_key ? "已配置 · 留空保持不变" : "sk-... 留空则跳过翻译";
  // 代理只显示端口号，去掉 http://127.0.0.1: 前缀
  let proxyVal = cfg.proxy||"";
  proxyVal = proxyVal.replace(/^https?:\/\/127\.0\.0\.1:/, "").replace(/^https?:\/\/localhost:/, "");
  document.getElementById("cfg-proxy").value = /^\d+$/.test(proxyVal) ? proxyVal : "";
  document.getElementById("cfg-use-proxy").checked = cfg.use_proxy||false;
  if (!cfg.exists) {
    document.getElementById("settings-msg").textContent = "首次使用，请配置后保存";
    document.getElementById("settings-msg").className = "status-msg err";
  }
}
function closeSettings() {
  document.getElementById("settings-overlay").classList.remove("show");
}
async function saveSettings() {
  let proxyVal = document.getElementById("cfg-proxy").value.trim();
  // 纯数字 → 自动补全; 已是完整URL → 保留; 空 → 不设置
  if (/^\d+$/.test(proxyVal)) {
    proxyVal = "http://127.0.0.1:" + proxyVal;
  }
  const payload = {
    github_token: document.getElementById("cfg-github").value.trim(),
    deepseek_api_key: document.getElementById("cfg-deepseek").value.trim(),
    proxy: proxyVal,
    use_proxy: document.getElementById("cfg-use-proxy").checked,
  };
  const res = await fetch("/api/config", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
  const data = await res.json();
  const msg = document.getElementById("settings-msg");
  if (data.ok) {
    msg.textContent = "CONFIG SAVED · 配置已保存，下次运行时生效";
    msg.className = "status-msg ok";
    const st = document.getElementById("status-text");
    st.textContent = "CONFIG UPDATED";
    setTimeout(()=>{ st.textContent="STANDBY"; closeSettings(); }, 1500);
  } else {
    msg.textContent = "SAVE FAILED";
    msg.className = "status-msg err";
  }
}

// 首次启动：无配置时自动弹窗
(async function(){
  const res = await fetch("/api/config");
  const cfg = await res.json();
  if (!cfg.exists) {
    setTimeout(() => openSettings(), 800);
  }
})();

// 关闭页面时通知后台退出
window.addEventListener("beforeunload", () => {
  navigator.sendBeacon("/api/shutdown");
});
</script>
</body>
</html>

</html>"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

def _safe_print(msg):
    """忽略控制台输出错误（--windowed模式无控制台）"""
    try:
        print(msg)
    except (OSError, UnicodeEncodeError):
        pass

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000, help="端口号")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    port = args.port
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")

    _safe_print(f"AI Hotspot Daily - Desktop App")
    _safe_print(f"   URL: http://127.0.0.1:{port}")

    from waitress import serve
    serve(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
