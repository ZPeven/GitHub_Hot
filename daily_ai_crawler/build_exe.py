#!/usr/bin/env python3
"""PyInstaller 打包脚本 — 生成独立 .exe 文件"""
import os, sys, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))

# ── 1. 检查/安装 PyInstaller ──────────────
try:
    import PyInstaller
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

# ── 2. 找图标 ────────────────────────────
icon = os.path.join(os.path.dirname(BASE), "图标.png")
if not os.path.exists(icon):
    # 尝试其他位置
    for p in [os.path.join(BASE, "图标.png"), os.path.join(BASE, "..", "图标.png")]:
        if os.path.exists(p):
            icon = p
            break
    else:
        print("⚠️ 未找到图标文件，使用默认图标")
        icon = None

# ── 3. 构建命令 ──────────────────────────
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",          # 无控制台窗口
    "--name", "AI热点日报",
    "--add-data", f"{BASE}{os.sep}reports{os.pathsep}reports",
    "--add-data", f"{BASE}{os.sep}config.local.yaml.example{os.pathsep}.",
    "--add-data", f"{BASE}{os.sep}sources.yaml{os.pathsep}.",
    "--add-data", f"{BASE}{os.sep}lamda_members.json{os.pathsep}.",
    "--hidden-import", "flask",
    "--hidden-import", "waitress",
    "--hidden-import", "aiohttp",
    "--hidden-import", "jieba",
    "--hidden-import", "feedparser",
    "--hidden-import", "bs4",
    "--hidden-import", "lxml",
    "--hidden-import", "yaml",
    "--hidden-import", "simhash",
    "--hidden-import", "urllib.robotparser",
    "--clean",
    "--noconfirm",
]

if icon and os.path.exists(icon):
    cmd.extend(["--icon", icon])

cmd.append(os.path.join(BASE, "app.py"))

print("🔨 开始打包...")
print("   " + " ".join(cmd))
subprocess.check_call(cmd, cwd=BASE)

# ── 4. 完成提示 ──────────────────────────
dist = os.path.join(BASE, "dist", "AI热点日报.exe")
if os.path.exists(dist):
    size_mb = os.path.getsize(dist) / 1024 / 1024
    print(f"\n✅ 打包完成!")
    print(f"   📦 {dist}")
    print(f"   📏 {size_mb:.1f} MB")
    print(f"\n使用时将以下文件放在 exe 同目录:")
    print(f"   - config.local.yaml (你的配置文件)")
    print(f"   - sources.yaml (已内置)")
    print(f"   - reports/ 目录会自动创建")
