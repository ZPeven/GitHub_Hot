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
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(sys.executable)
else:
    _EXE_DIR = os.path.dirname(os.path.abspath(__file__))

# 工作目录设为 exe 所在目录
os.chdir(_EXE_DIR)

# 覆盖 config 中的路径
import config
config.BASE_DIR = _EXE_DIR
config.REPORTS_DIR = os.path.join(_EXE_DIR, "reports")
config.DB_FILE = os.path.join(_EXE_DIR, "crawler.db")
config.SOURCES_FILE = os.path.join(_EXE_DIR, "sources.yaml")

# lamda_members 路径也修复
import processors.lamda_matcher as lm
lm._MEMBERS_FILE = os.path.join(_EXE_DIR, "lamda_members.json")

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
# 爬虫执行
# ═══════════════════════════════════════════

def _run_crawl():
    global _crawl_status
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "main.py"), "-v"],
            capture_output=True, text=True, timeout=180,
            cwd=BASE_DIR,
        )
        _crawl_status["log"] = result.stdout.split("\n")[-30:]
        _crawl_status["log"].append(f"--- stderr ---")
        _crawl_status["log"].extend(result.stderr.split("\n")[-10:])
        _crawl_status["success"] = result.returncode == 0
    except subprocess.TimeoutExpired:
        _crawl_status["success"] = False
        _crawl_status["log"].append("⏱️ 爬取超时 (180s)")
    except Exception as e:
        _crawl_status["success"] = False
        _crawl_status["log"].append(f"❌ {e}")
    _crawl_status["running"] = False


# ═══════════════════════════════════════════
# 前端页面
# ═══════════════════════════════════════════

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 热点日报</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔥</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@300;400;500&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --ink: #0d0b09;
  --parchment: #faf6f0;
  --parchment-dim: #ede4d8;
  --paper: #fffef9;
  --gold: #b8860b;
  --gold-light: #d4a574;
  --amber: #e8c56d;
  --bronze: #8b6914;
  --copper: #c77d43;
  --charcoal: #2c2416;
  --smoke: #6b5e4a;
  --clay: #9e8b74;
  --sage: #7d8a6e;
  --rose: #c17e7e;
  --slate: #4a5568;
  --radius: 10px;
  --radius-sm: 6px;
  --shadow-sm: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --shadow: 0 4px 24px rgba(0,0,0,.08), 0 1px 4px rgba(0,0,0,.04);
  --shadow-lg: 0 20px 60px rgba(0,0,0,.12), 0 4px 16px rgba(0,0,0,.06);
  --transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'Noto Sans SC', system-ui, -apple-system, sans-serif;
  background: var(--parchment);
  color: var(--charcoal);
  height: 100vh;
  display: flex;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

/* ── Sidebar ─────────────────────────── */
#sidebar {
  width: 280px; min-width: 280px;
  background: var(--ink);
  color: var(--parchment-dim);
  display: flex; flex-direction: column; overflow: hidden;
  position: relative;
  z-index: 10;
  box-shadow: 4px 0 40px rgba(0,0,0,.15);
}
#sidebar::after {
  content: '';
  position: absolute; inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(255,255,255,.008) 2px, rgba(255,255,255,.008) 4px
  );
  pointer-events: none;
}
.sidebar-header {
  padding: 28px 24px 20px;
  border-bottom: 1px solid rgba(255,255,255,.06);
}
.sidebar-header .brand {
  font-family: 'Cormorant Garamond', 'Noto Serif SC', serif;
  font-size: 26px; font-weight: 700; letter-spacing: 1px;
  background: linear-gradient(135deg, var(--gold-light), var(--amber), var(--copper));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.sidebar-header .subtitle {
  font-size: 11px; color: rgba(255,255,255,.35);
  letter-spacing: 3px; text-transform: uppercase; margin-top: 4px;
}
.sidebar-divider {
  margin: 0 24px; height: 1px;
  background: linear-gradient(90deg, rgba(255,255,255,.08), transparent);
}
#report-list {
  flex: 1; overflow-y: auto; padding: 12px 12px 80px;
  scroll-behavior: smooth;
}
#report-list::-webkit-scrollbar { width: 4px; }
#report-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 2px; }

.report-item {
  padding: 14px 16px; margin-bottom: 4px; border-radius: var(--radius);
  cursor: pointer; transition: all var(--transition);
  border: 1px solid transparent;
  position: relative; overflow: hidden;
}
.report-item::before {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(135deg, rgba(212,165,116,.08), transparent 60%);
  opacity: 0; transition: opacity var(--transition);
}
.report-item:hover { background: rgba(255,255,255,.04); border-color: rgba(255,255,255,.06); }
.report-item:hover::before { opacity: 1; }
.report-item.active {
  background: rgba(212,165,116,.1);
  border-color: rgba(212,165,116,.25);
  box-shadow: inset 0 0 0 1px rgba(212,165,116,.15);
}
.report-item.active::before { opacity: 1; }
.report-item .r-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: var(--clay); letter-spacing: .5px;
  display: flex; align-items: center; gap: 8px;
}
.report-item .r-date .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--copper); opacity: 0;
  transition: opacity var(--transition);
}
.report-item.active .r-date .dot { opacity: 1; }
.report-item .r-title {
  font-size: 14px; font-weight: 500; margin-top: 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  color: rgba(255,255,255,.8);
  letter-spacing: .3px;
}
.report-item.active .r-title { color: rgba(255,255,255,.95); }

.sidebar-footer {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 16px 20px;
  background: linear-gradient(0deg, var(--ink) 60%, transparent);
  z-index: 2;
}
#btn-crawl {
  width: 100%; padding: 14px; border: none; border-radius: var(--radius);
  background: linear-gradient(135deg, var(--gold), var(--copper));
  color: #fff; font-family: 'Noto Sans SC', sans-serif;
  font-size: 14px; font-weight: 600; letter-spacing: 1px;
  cursor: pointer; transition: all var(--transition);
  box-shadow: 0 4px 20px rgba(184,134,11,.3);
  position: relative; overflow: hidden;
}
#btn-crawl::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(135deg, transparent 40%, rgba(255,255,255,.15));
  transition: opacity var(--transition);
}
#btn-crawl:hover { transform: translateY(-1px); box-shadow: 0 8px 30px rgba(184,134,11,.4); }
#btn-crawl:active { transform: translateY(0); }
#btn-crawl:disabled {
  opacity: .6; cursor: not-allowed; transform: none;
  animation: pulse-gold 2s ease-in-out infinite;
}
@keyframes pulse-gold {
  0%,100% { box-shadow: 0 4px 20px rgba(184,134,11,.3); }
  50% { box-shadow: 0 4px 30px rgba(184,134,11,.5); }
}
.sidebar-footer .status-text {
  font-size: 11px; color: rgba(255,255,255,.3); text-align: center;
  margin-top: 8px; letter-spacing: .5px;
}

/* ── Main Content ─────────────────────── */
#main {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: var(--paper);
}
#toolbar {
  padding: 16px 32px;
  border-bottom: 1px solid var(--parchment-dim);
  display: flex; align-items: center; gap: 16px;
  background: rgba(255,255,255,.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 5;
}
#toolbar .doc-title {
  flex: 1; font-family: 'Cormorant Garamond', serif;
  font-size: 20px; font-weight: 600; color: var(--charcoal);
  letter-spacing: .5px;
}
#view-mode {
  padding: 8px 14px; border: 1px solid var(--parchment-dim);
  border-radius: var(--radius-sm); background: #fff;
  font-family: 'Noto Sans SC', sans-serif; font-size: 12px;
  color: var(--charcoal); cursor: pointer; outline: none;
  transition: border-color var(--transition-fast);
}
#view-mode:focus { border-color: var(--gold-light); }
.btn-save {
  padding: 9px 22px; border: none; border-radius: var(--radius-sm);
  background: var(--ink); color: var(--amber); cursor: pointer;
  font-family: 'Noto Sans SC', sans-serif; font-size: 13px;
  font-weight: 500; letter-spacing: .5px;
  transition: all var(--transition-fast);
}
.btn-save:hover { background: #1a1610; }

#editor-area { flex: 1; display: flex; overflow: hidden; }
#editor {
  flex: 1; padding: 32px; background: #fffef9;
  color: var(--charcoal); border: none;
  border-right: 1px solid var(--parchment-dim);
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px; line-height: 1.85; resize: none; outline: none;
  tab-size: 2;
}
#editor::placeholder { color: var(--clay); font-style: italic; }
#editor:focus { background: #fffefa; }

#preview {
  flex: 1; padding: 32px 40px; overflow-y: auto; line-height: 1.9;
  font-size: 15px; color: #2c2416;
}
#preview h1 {
  font-family: 'Cormorant Garamond', serif;
  font-size: 32px; font-weight: 700; margin-bottom: 8px;
  color: var(--charcoal); letter-spacing: 1px;
}
#preview h2 {
  font-family: 'Cormorant Garamond', serif;
  font-size: 22px; font-weight: 600; margin: 32px 0 12px;
  color: var(--bronze); letter-spacing: .5px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--parchment-dim);
}
#preview h3 {
  font-size: 16px; font-weight: 600; margin: 20px 0 8px; color: var(--copper);
}
#preview table {
  border-collapse: collapse; width: 100%; margin: 16px 0;
  font-size: 13px; border-radius: var(--radius-sm); overflow: hidden;
  box-shadow: var(--shadow-sm);
}
#preview th, #preview td {
  border: 1px solid var(--parchment-dim); padding: 8px 14px; text-align: left;
}
#preview th {
  background: var(--ink); color: var(--gold-light);
  font-weight: 500; font-size: 12px; letter-spacing: .5px;
}
#preview tr:nth-child(even) td { background: rgba(0,0,0,.012); }
#preview a {
  color: var(--bronze); text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color var(--transition-fast);
}
#preview a:hover { border-bottom-color: var(--copper); }
#preview blockquote {
  border-left: 3px solid var(--gold-light); padding: 8px 18px;
  margin: 12px 0; color: var(--smoke); font-style: italic;
  background: rgba(212,165,116,.06); border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
#preview code {
  background: rgba(0,0,0,.04); padding: 2px 7px;
  border-radius: 4px; font-family: 'JetBrains Mono', monospace;
  font-size: 12px; color: var(--copper);
}
#preview hr { border: none; border-top: 1px solid var(--parchment-dim); margin: 32px 0; }

/* ── Empty State ──────────────────────── */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 16px;
  color: var(--clay);
}
.empty-state .icon {
  font-size: 56px; opacity: .5;
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0%,100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
.empty-state p { font-size: 15px; letter-spacing: .5px; }

/* ── Welcome Hero ─────────────────────── */
.welcome-hero {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 20px;
}
.welcome-hero h1 {
  font-family: 'Cormorant Garamond', serif;
  font-size: 48px; font-weight: 700; color: var(--charcoal);
  letter-spacing: 2px;
}
.welcome-hero .tagline {
  font-size: 15px; color: var(--clay); letter-spacing: 1px;
}
.welcome-hero .shortcuts {
  margin-top: 32px; display: flex; gap: 24px;
}
.welcome-hero .shortcut {
  padding: 10px 20px; border-radius: var(--radius);
  border: 1px solid var(--parchment-dim); font-size: 12px;
  color: var(--smoke); letter-spacing: .5px;
  font-family: 'JetBrains Mono', monospace;
}
.welcome-hero .shortcut kbd {
  padding: 2px 8px; border-radius: 4px;
  background: var(--parchment-dim); font-family: inherit;
}

/* ── Log Overlay ───────────────────────── */
#log-overlay {
  position: fixed; bottom: 24px; right: 24px;
  width: 420px; max-height: 320px; z-index: 100;
  background: var(--ink); border: 1px solid rgba(255,255,255,.1);
  border-radius: 16px; overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,.4);
  display: none;
  animation: slideUp .35s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
#log-overlay.show { display: flex; flex-direction: column; }
.log-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid rgba(255,255,255,.06);
}
.log-header span {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: var(--gold-light); letter-spacing: 1px;
  display: flex; align-items: center; gap: 8px;
}
.log-header .spinner {
  width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.1);
  border-top-color: var(--amber); border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.btn-close {
  width: 28px; height: 28px; border: none; border-radius: 50%;
  background: rgba(255,255,255,.06); color: rgba(255,255,255,.5);
  cursor: pointer; font-size: 16px; display: flex;
  align-items: center; justify-content: center;
  transition: all var(--transition-fast);
  font-family: inherit; line-height: 1;
}
.btn-close:hover { background: rgba(255,255,255,.12); color: #fff; }
.log-body {
  flex: 1; overflow-y: auto; padding: 12px 18px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  line-height: 1.7;
}
.log-body .line { white-space: pre-wrap; margin: 1px 0; padding: 1px 0; }
.log-body .line.ok { color: var(--sage); }
.log-body .line.warn { color: var(--amber); }
.log-body .line.err { color: var(--rose); }
.log-body .line.info { color: var(--clay); }
.log-body::-webkit-scrollbar { width: 3px; }
.log-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,.08); border-radius: 2px; }
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sidebar">
  <div class="sidebar-header">
    <div class="brand">AI 热点日报</div>
    <div class="subtitle">Daily Intelligence Briefing</div>
  </div>
  <div class="sidebar-divider"></div>
  <div id="report-list"></div>
  <div class="sidebar-footer">
    <button id="btn-crawl" onclick="startCrawl()">开始抓取</button>
    <p class="status-text" id="status-text">就绪</p>
  </div>
</div>

<!-- Main Content -->
<div id="main">
  <div id="toolbar">
    <span class="doc-title" id="current-title">欢迎使用 AI 热点日报</span>
    <select id="view-mode" onchange="setViewMode(this.value)">
      <option value="split">编辑 + 预览</option>
      <option value="edit">仅编辑</option>
      <option value="preview">仅预览</option>
    </select>
    <button class="btn-save" onclick="saveReport()">保存</button>
  </div>
  <div id="editor-area">
    <textarea id="editor" placeholder="选择左侧报告开始编辑..."
              oninput="onEditorChange()" onkeydown="onEditorKey(event)"></textarea>
    <div id="preview">
      <div class="welcome-hero">
        <h1>AI 热点日报</h1>
        <p class="tagline">每日 AI 技术前沿情报 · 双语对照 · 可编辑预览</p>
        <div class="shortcuts">
          <div class="shortcut"><kbd>Ctrl+S</kbd> 保存</div>
          <div class="shortcut"><kbd>点击左侧</kbd> 切换报告</div>
          <div class="shortcut"><kbd>开始抓取</kbd> 获取最新</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Crawl Log Overlay -->
<div id="log-overlay">
  <div class="log-header">
    <span><span class="spinner" id="log-spinner"></span> 抓取日志</span>
    <button class="btn-close" onclick="hideLogOverlay()" title="关闭">×</button>
  </div>
  <div class="log-body" id="log-body"></div>
</div>

<script>
let currentDate = null, currentFilename = null, originalContent = "", pollTimer = null;

marked.setOptions({ breaks: true, gfm: true });
loadReports();

// ── Report list ──
async function loadReports() {
  const res = await fetch("/api/reports");
  const reports = await res.json();
  const list = document.getElementById("report-list");
  if (reports.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="icon">&#x1F4ED;</div><p>暂无报告</p><p style="font-size:12px;color:var(--clay)">点击下方按钮开始首次抓取</p></div>`;
    return;
  }
  list.innerHTML = reports.map(r => `<div class="report-item${currentDate===r.date?' active':''}" onclick="openReport('${r.date}')"><div class="r-date"><span class="dot"></span>${r.date}</div><div class="r-title">${r.title}</div></div>`).join("");
}

async function openReport(date) {
  const res = await fetch("/api/reports/" + date);
  const data = await res.json();
  if (data.error) return;
  currentDate = date; currentFilename = data.filename; originalContent = data.content;
  document.getElementById("editor").value = data.content;
  document.getElementById("current-title").textContent = data.filename;
  renderPreview(data.content);
  loadReports();
}

// ── Editor ──
function onEditorChange() {
  renderPreview(document.getElementById("editor").value);
}
function onEditorKey(e) {
  if ((e.ctrlKey||e.metaKey) && e.key === 's') { e.preventDefault(); saveReport(); }
}
function renderPreview(md) {
  document.getElementById("preview").innerHTML = marked.parse(md || "");
}
function setViewMode(mode) {
  const ed = document.getElementById("editor"), pv = document.getElementById("preview");
  if (mode === "split") { ed.style.display=""; pv.style.display=""; ed.style.flex="1"; pv.style.flex="1"; }
  else if (mode === "edit") { ed.style.display=""; pv.style.display="none"; ed.style.flex="1"; }
  else { ed.style.display="none"; pv.style.display=""; pv.style.flex="1"; }
}

// ── Save ──
async function saveReport() {
  if (!currentDate) return;
  const content = document.getElementById("editor").value;
  await fetch("/api/reports/" + currentDate, {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({content, filename: currentFilename})
  });
  originalContent = content;
  const st = document.getElementById("status-text");
  st.textContent = "已保存 " + new Date().toLocaleTimeString();
  setTimeout(() => { if (st.textContent.includes("已保存")) st.textContent = "就绪"; }, 2000);
}

// ── Crawl ──
async function startCrawl() {
  const btn = document.getElementById("btn-crawl");
  if (btn.disabled) return;
  btn.disabled = true; btn.textContent = "抓取中...";
  showLogOverlay(); document.getElementById("log-spinner").style.display = "";
  await fetch("/api/crawl", {method:"POST"});
  pollTimer = setInterval(pollCrawlStatus, 1500);
}
async function pollCrawlStatus() {
  const res = await fetch("/api/crawl/status");
  const s = await res.json();
  if (!s.running) { clearInterval(pollTimer); document.getElementById("log-spinner").style.display = "none"; }
  updateLogBody(s.log||[]);
  const btn = document.getElementById("btn-crawl"), status = document.getElementById("status-text");
  if (!s.running) {
    btn.disabled = false; btn.textContent = "开始抓取";
    status.textContent = s.success ? "抓取完成" : "抓取失败";
    loadReports();
    const first = document.querySelector("#report-list .report-item");
    if (first) first.click();
  }
}
function showLogOverlay() {
  const el = document.getElementById("log-overlay");
  el.classList.add("show"); document.getElementById("log-body").innerHTML = "";
}
function hideLogOverlay() {
  document.getElementById("log-overlay").classList.remove("show");
}
function updateLogBody(lines) {
  const el = document.getElementById("log-body");
  el.innerHTML = lines.map(l => {
    let cls = "info";
    if (l.includes("✅")) cls = "ok";
    else if (l.includes("⚠️")||l.includes("超时")) cls = "warn";
    else if (l.includes("❌")||l.includes("出错")) cls = "err";
    return '<div class="line '+cls+'">'+l+'</div>';
  }).join("");
  el.scrollTop = el.scrollHeight;
}
</script>
</body>
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
