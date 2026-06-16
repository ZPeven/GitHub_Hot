"""
从LAMDA成员页面提取所有人员姓名
用于后续精确作者匹配
"""

import re
import json
import sys
import os

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def extract_from_html(content: str) -> dict:
    """从LAMDA页面HTML提取所有人员"""
    result = {
        "directors": [],    # 负责人
        "faculty": [],       # 教师
        "visiting_prof": [], # 访问教授
        "doctors": [],       # 博士生
        "masters": [],       # 硕士生
        "all_names": [],     # 所有人名（用于匹配）
    }

    # 1. 提取HTML中的静态成员（负责人等）
    # 周志华在静态HTML中
    static_names = re.findall(
        r'<a[^>]*href="http://cs\.nju\.edu\.cn/[^"]*"[^>]*>([^<]+)</a>',
        content
    )
    for name in static_names:
        name = name.strip()
        if name and name not in result["all_names"]:
            result["directors"].append(name)
            result["all_names"].append(name)

    # 2. 提取 teachers_students JavaScript 数组
    # 查找数组定义范围
    match = re.search(r'let teachers_students = (\[.*?\]);\s*(?:let|var|<script)', content, re.DOTALL)
    if not match:
        match = re.search(r'teachers_students = (\[.*?\}\])\s*;\s*$', content, re.DOTALL | re.MULTILINE)
    if not match:
        # 尝试更宽松的匹配
        match = re.search(r'teachers_students\s*=\s*(\[.*?\])\s*;\s*(?:for|document|let|var|<)', content, re.DOTALL)

    if match:
        js_array_text = match.group(1)

        # JavaScript对象转Python - 简化处理，逐行提取
        # 提取教师姓名
        teacher_names = re.findall(r'"name":\s*"([^"]+)"', js_array_text)
        if teacher_names:
            # 第一个是教师名
            result["faculty"] = teacher_names[:2]  # 高尉, 姜远 (approximate)
            result["all_names"].extend(teacher_names)

        # 提取所有学生名
        # 带链接的学生
        student_matches = re.findall(r'"name":\s*"([^"]+)"', js_array_text)
        # 按约定：teacher_names后的是学生

    # 3. 也尝试另一种匹配 - 直接提取页面上所有中文名模式
    # 中文字符2-4个作为姓名
    cn_names = re.findall(r'>([^\x00-\x7f]{2,4})</a>', content)
    cn_names += re.findall(r'"name":\s*"([^\x00-\x7f]{2,4})"', content)

    seen = set(result["all_names"])
    for name in cn_names:
        name = name.strip()
        if name and name not in seen and len(name) >= 2 and len(name) <= 4:
            seen.add(name)
            result["all_names"].append(name)

    return result


def extract_all_from_curl():
    """从curl获取的LAMDA页面提取"""
    import subprocess
    import tempfile

    # 从config获取代理
    from config import PROXIES

    proxy_arg = f"--proxy {PROXIES['http']}" if PROXIES else ""

    # 主成员页
    cmd = f'curl -s {proxy_arg} --max-time 15 "https://www.lamda.nju.edu.cn/CH.People.ashx"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    content = result.stdout

    if not content:
        print("ERROR: Could not fetch LAMDA page")
        return

    data = extract_from_html(content)

    # 也解析子页面（博士生、硕士生等）
    sub_pages = [
        "CH.PhD_student.ashx",
        "CH.MSc_students.ashx",
        "CH.postdoctoral_fellow.ashx",
        "CH.visiting_student.ashx",
    ]

    for sub_page in sub_pages:
        sub_cmd = f'curl -s {proxy_arg} --max-time 15 "https://www.lamda.nju.edu.cn/{sub_page}"'
        sub_result = subprocess.run(sub_cmd, shell=True, capture_output=True, text=True)
        if sub_result.stdout:
            sub_data = extract_from_html(sub_result.stdout)
            for name in sub_data["all_names"]:
                if name not in data["all_names"]:
                    data["all_names"].append(name)

    # 输出
    print(f"=== LAMDA 成员摘要 ===")
    print(f"负责人: {data['directors']}")
    print(f"教师: {data['faculty']}")
    print(f"所有人名 ({len(data['all_names'])}人):")
    for name in sorted(data['all_names']):
        print(f"  - {name}")

    # 保存到配置
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lamda_members.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到: {output_path}")

    # 打印Python格式的名单
    print(f"\n=== 可直接用于config.py ===")
    print(f"LAMDA_MEMBERS = [")
    for name in sorted(data['all_names']):
        print(f'    "{name}",')
    print(f"]")
    print(f"# 共 {len(data['all_names'])} 人")


if __name__ == "__main__":
    extract_all_from_curl()
