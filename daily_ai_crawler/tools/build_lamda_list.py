"""
构建完整的LAMDA成员名单（含教师+学生）
从页面HTML和JavaScript数据中提取
"""
import re
import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROXIES

proxy_arg = f"--proxy {PROXIES['http']}" if PROXIES else ""

def fetch_page(url):
    cmd = f'curl -s {proxy_arg} --max-time 15 "{url}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout

def extract_names(html):
    names = set()

    # 1. JS数据中的name字段 (含教师和学生)
    for m in re.finditer(r'^\s*name:\s*"([^"]+)"', html, re.MULTILINE):
        name = m.group(1).strip()
        if not name:
            continue
        # 递归展开中文括号中的名字 (如"LAMDA-RL 小组（俞扬、章宗长、袁雷、许天）")
        bracket_match = re.search(r'[（(]([^）)]+)[）)]', name)
        if bracket_match:
            inner = bracket_match.group(1)
            for n in re.split(r'[、，,]', inner):
                n = n.strip()
                if n and len(n) >= 2:
                    names.add(n)
        else:
            # 过滤明显的非人名
            if not re.match(r'^[A-Za-z\s\-]+$', name) or len(name) > 25:
                if len(name) >= 2 and not name.startswith("http"):
                    names.add(name)

    # 2. HTML静态姓名 (周志华等)
    for m in re.finditer(r'<a[^>]*>\s*([^\x00-\x7f]{2,4})\s*</a>', html):
        name = m.group(1).strip()
        if name and '一' <= name[0] <= '鿿':
            names.add(name)

    # 3. 过滤非人名条目
    filtered = set()
    for name in names:
        # 排除分组标签
        if any(kw in name for kw in ['小组', '学生', '老师', '教授', '博士']):
            continue
        # 排除纯英文超长名
        if re.match(r'^[A-Za-z\s\-]{25,}$', name):
            continue
        # 排除纯数字或特殊字符
        if re.match(r'^[\d\s\.\-_]+$', name):
            continue
        filtered.add(name)

    return filtered


def main():
    all_names = set()

    # 主页面
    print("Fetching main page...")
    html = fetch_page("https://www.lamda.nju.edu.cn/CH.People.ashx")
    names = extract_names(html)
    print(f"  Main page: {len(names)} names")
    all_names.update(names)

    # 子页面
    sub_pages = [
        ("CH.PhD_student.ashx", "PhD students"),
        ("CH.MSc_students.ashx", "MSc students"),
        ("CH.postdoctoral_fellow.ashx", "Postdocs"),
        ("CH.visiting_student.ashx", "Visiting students"),
    ]
    for page, label in sub_pages:
        url = f"https://www.lamda.nju.edu.cn/{page}"
        print(f"Fetching {label}...")
        html = fetch_page(url)
        names = extract_names(html)
        new = names - all_names
        print(f"  {label}: {len(names)} names ({len(new)} new)")
        all_names.update(names)

    # 最终整理
    sorted_names = sorted(all_names)
    print(f"\n=== Final: {len(sorted_names)} unique LAMDA members ===")

    # 验证关键教师
    key_teachers = ['周志华', '姜远', '高尉', '黎铭', '俞扬', '李宇峰',
                    '王魏', '吴建鑫', '钱超', '詹德川', '张利军', '叶翰嘉',
                    '赵鹏', '章宗长', '袁雷', '许天', '李武军']
    missing = [t for t in key_teachers if t not in all_names]
    if missing:
        print(f"WARNING: Missing teachers: {missing}")

    # 保存
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "lamda_members.json")
    data = {
        "source": "https://www.lamda.nju.edu.cn/CH.People.ashx",
        "total": len(sorted_names),
        "members": sorted_names,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved to: {output_path}")

    # 输出Python格式
    print(f"\n# LAMDA_MEMBERS = [")
    for name in sorted_names:
        print(f'  "{name}",')
    print(f"# ]")


if __name__ == "__main__":
    main()
