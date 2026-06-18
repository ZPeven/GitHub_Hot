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

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 热点日报</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔥</text></svg>">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg: #1e1e2e; --sidebar-bg: #181825; --card-bg: #252538;
  --text: #cdd6f4; --text-muted: #a6adc8; --accent: #cba6f7;
  --border: #313244; --hover: #2a2a3c; --danger: #f38ba8;
  --green: #a6e3a1; --yellow: #f9e2af;
}
body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); height:100vh; display:flex; overflow:hidden; }
/* Sidebar */
#sidebar { width:260px; min-width:260px; background:var(--sidebar-bg); border-right:1px solid var(--border); display:flex; flex-direction:column; overflow:hidden; }
#sidebar h2 { padding:16px; font-size:16px; color:var(--accent); border-bottom:1px solid var(--border); display:flex; align-items:center; gap:8px; }
#report-list { flex:1; overflow-y:auto; padding:8px; }
#report-list .item { padding:10px 12px; border-radius:8px; cursor:pointer; margin-bottom:4px; transition:background .15s; border:1px solid transparent; }
#report-list .item:hover { background:var(--hover); }
#report-list .item.active { background:var(--hover); border-color:var(--accent); }
#report-list .item .date { font-size:12px; color:var(--text-muted); }
#report-list .item .title { font-size:13px; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
#sidebar .footer { padding:12px; border-top:1px solid var(--border); }
#btn-crawl { width:100%; padding:10px; border:none; border-radius:8px; background:var(--accent); color:#1e1e2e; font-weight:bold; cursor:pointer; font-size:14px; transition:opacity .2s; }
#btn-crawl:hover { opacity:.85; }
#btn-crawl:disabled { opacity:.5; cursor:not-allowed; }
.status-bar { font-size:11px; color:var(--text-muted); text-align:center; margin-top:6px; }
/* Main */
#main { flex:1; display:flex; flex-direction:column; overflow:hidden; }
#toolbar { padding:10px 16px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:12px; }
#toolbar select, #toolbar button { padding:6px 12px; border:1px solid var(--border); border-radius:6px; background:var(--card-bg); color:var(--text); cursor:pointer; font-size:13px; }
#toolbar button:hover { background:var(--hover); }
#toolbar .save-btn { background:var(--accent); color:#1e1e2e; border-color:var(--accent); font-weight:bold; }
#editor-area { flex:1; display:flex; overflow:hidden; }
#editor { flex:1; padding:20px; background:var(--card-bg); color:var(--text); border:none; border-right:1px solid var(--border); font-family:'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size:13px; line-height:1.7; resize:none; outline:none; tab-size:2; }
#preview { flex:1; padding:20px 30px; overflow-y:auto; line-height:1.8; }
#preview h1 { font-size:22px; margin-bottom:12px; color:var(--accent); }
#preview h2 { font-size:17px; margin:20px 0 10px; color:var(--green); border-bottom:1px solid var(--border); padding-bottom:6px; }
#preview h3 { font-size:14px; margin:14px 0 6px; color:var(--yellow); }
#preview table { border-collapse:collapse; width:100%; margin:10px 0; font-size:13px; }
#preview th, #preview td { border:1px solid var(--border); padding:6px 10px; text-align:left; }
#preview th { background:var(--hover); }
#preview a { color:var(--accent); }
#preview blockquote { border-left:3px solid var(--accent); padding-left:14px; color:var(--text-muted); margin:8px 0; }
#preview code { background:var(--hover); padding:2px 6px; border-radius:4px; font-size:12px; }
#preview hr { border:0; border-top:1px solid var(--border); margin:16px 0; }
/* Crawl log overlay */
#log-overlay { position:fixed; bottom:0; right:0; width:420px; max-height:260px; background:var(--sidebar-bg); border:1px solid var(--border); border-radius:12px 0 0 0; overflow-y:auto; padding:14px; font-size:11px; font-family:monospace; display:none; z-index:99; }
#log-overlay.show { display:block; }
#log-overlay .line { white-space:pre-wrap; margin:2px 0; }
#log-overlay .line.ok { color:var(--green); }
#log-overlay .line.warn { color:var(--yellow); }
#log-overlay .line.err { color:var(--danger); }
/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:var(--text-muted); gap:12px; }
.empty-state .icon { font-size:48px; }
.empty-state p { font-size:15px; }
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sidebar">
  <h2>🔥 AI 热点日报</h2>
  <div id="report-list"></div>
  <div class="footer">
    <button id="btn-crawl" onclick="startCrawl()">🚀 开始抓取</button>
    <div class="status-bar" id="status-text">就绪</div>
  </div>
</div>

<!-- Main -->
<div id="main">
  <div id="toolbar">
    <span id="current-title" style="font-weight:bold;flex:1"></span>
    <button class="save-btn" onclick="saveReport()">💾 保存</button>
    <select id="view-mode" onchange="setViewMode(this.value)">
      <option value="split">编辑 | 预览</option>
      <option value="edit">仅编辑</option>
      <option value="preview">仅预览</option>
    </select>
  </div>
  <div id="editor-area">
    <textarea id="editor" placeholder="选择左侧报告开始编辑..."
              oninput="onEditorChange()" onkeydown="onEditorKey(event)"></textarea>
    <div id="preview"></div>
  </div>
</div>

<!-- Crawl log -->
<div id="log-overlay"></div>

<script>
// ── State ──
let currentDate = null;
let currentFilename = null;
let originalContent = "";
let pollTimer = null;

// ── Init ──
marked.setOptions({ breaks: true, gfm: true });
loadReports();

// ── Report list ──
async function loadReports() {
  const res = await fetch("/api/reports");
  const reports = await res.json();
  const list = document.getElementById("report-list");
  if (reports.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="icon">📭</div><p>暂无报告</p><p style="font-size:12px">点击下方按钮开始抓取</p></div>`;
    return;
  }
  list.innerHTML = reports.map(r => `
    <div class="item${currentDate===r.date?' active':''}" onclick="openReport('${r.date}')">
      <div class="date">📅 ${r.date}</div>
      <div class="title">${r.title}</div>
    </div>
  `).join("");
}

async function openReport(date) {
  const res = await fetch(`/api/reports/${date}`);
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  currentDate = date;
  currentFilename = data.filename;
  originalContent = data.content;
  document.getElementById("editor").value = data.content;
  document.getElementById("current-title").textContent = `📄 ${data.filename}`;
  renderPreview(data.content);
  loadReports();
}

// ── Editor ──
function onEditorChange() {
  renderPreview(document.getElementById("editor").value);
}

function onEditorKey(e) {
  if ((e.ctrlKey||e.metaKey) && e.key === 's') {
    e.preventDefault();
    saveReport();
  }
}

function renderPreview(md) {
  document.getElementById("preview").innerHTML = marked.parse(md || "");
}

function setViewMode(mode) {
  const editor = document.getElementById("editor");
  const preview = document.getElementById("preview");
  if (mode === "split") { editor.style.display=""; preview.style.display=""; editor.style.flex="1"; preview.style.flex="1"; }
  else if (mode === "edit") { editor.style.display=""; preview.style.display="none"; editor.style.flex="1"; }
  else { editor.style.display="none"; preview.style.display=""; preview.style.flex="1"; }
}

// ── Save ──
async function saveReport() {
  if (!currentDate) return;
  const content = document.getElementById("editor").value;
  await fetch(`/api/reports/${currentDate}`, {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({content, filename: currentFilename})
  });
  originalContent = content;
  const st = document.getElementById("status-text");
  st.textContent = "✅ 已保存 " + new Date().toLocaleTimeString();
  setTimeout(() => { if (st.textContent.includes("已保存")) st.textContent = "就绪"; }, 2000);
}

// ── Crawl ──
async function startCrawl() {
  const btn = document.getElementById("btn-crawl");
  const status = document.getElementById("status-text");
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = "⏳ 抓取中...";
  status.textContent = "启动中...";
  showLogOverlay();

  await fetch("/api/crawl", {method:"POST"});
  pollTimer = setInterval(pollCrawlStatus, 1500);
}

async function pollCrawlStatus() {
  const res = await fetch("/api/crawl/status");
  const s = await res.json();
  const btn = document.getElementById("btn-crawl");
  const status = document.getElementById("status-text");
  updateLogOverlay(s.log||[]);

  if (!s.running) {
    clearInterval(pollTimer);
    btn.disabled = false;
    btn.textContent = "🚀 开始抓取";
    status.textContent = s.success ? "✅ 抓取完成" : "❌ 抓取失败";
    loadReports();
    // Auto open latest
    const latest = document.querySelector("#report-list .item");
    if (latest) latest.click();
  } else {
    status.textContent = "⏳ 抓取中... " + (s.log?.length||0) + " 行日志";
  }
}

function showLogOverlay() {
  document.getElementById("log-overlay").classList.add("show");
  document.getElementById("log-overlay").innerHTML = "";
}
function updateLogOverlay(lines) {
  const el = document.getElementById("log-overlay");
  el.innerHTML = lines.map(l => {
    let cls = "";
    if (l.includes("✅")) cls = "ok";
    else if (l.includes("⚠️")||l.includes("超时")) cls = "warn";
    else if (l.includes("❌")||l.includes("出错")) cls = "err";
    return `<div class="line ${cls}">${l}</div>`;
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
