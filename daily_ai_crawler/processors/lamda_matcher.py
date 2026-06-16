"""
LAMDA 成员精确匹配器
— 用268人名单做中英文作者姓名匹配，远比 "Nanjing University" 字符串搜索精确
"""

import json
import os
import re

# 加载 LAMDA 成员名单
_MEMBERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lamda_members.json")
_LAMDA_MEMBERS: set[str] = set()
_ENGLISH_NAMES: set[str] = set()  # 英文/罗马化姓名

# ============================================================
# 核心教师 中→英 姓名映射
# (学术论文中最常见的署名形式)
# ============================================================
_FACULTY_EN_MAP = {
    # 中文名 → [常见英文署名变体]
    "周志华": ["Zhi-Hua Zhou", "Zhihua Zhou", "Zhou Z.-H.", "Zhou ZH"],
    "姜远":   ["Yuan Jiang", "Jiang Y."],
    "高尉":   ["Wei Gao", "Gao W."],
    "黎铭":   ["Ming Li", "Li M."],
    "俞扬":   ["Yang Yu", "Yu Y."],
    "李宇峰": ["Yu-Feng Li", "Yufeng Li", "Li Y.-F.", "Li YF"],
    "王魏":   ["Wei Wang", "Wang W."],
    "吴建鑫": ["Jian-Xin Wu", "Jianxin Wu", "Wu J.-X.", "Wu JX"],
    "钱超":   ["Chao Qian", "Qian C."],
    "詹德川": ["De-Chuan Zhan", "Dechuan Zhan", "Zhan D.-C.", "Zhan DC"],
    "张利军": ["Li-Jun Zhang", "Lijun Zhang", "Zhang L.-J.", "Zhang LJ"],
    "叶翰嘉": ["Han-Jia Ye", "Hanjia Ye", "Ye H.-J.", "Ye HJ"],
    "赵鹏":   ["Peng Zhao", "Zhao P."],
    "章宗长": ["Zong-Zhang Zhang", "Zongzhang Zhang", "Zhang Z.-Z."],
    "袁雷":   ["Lei Yuan", "Yuan L."],
    "许天":   ["Tian Xu", "Xu T."],
    "Cam":    ["Cam"],
}


def _load_members():
    global _LAMDA_MEMBERS, _ENGLISH_NAMES
    if _LAMDA_MEMBERS:
        return

    # 加载完整中文名单
    if os.path.exists(_MEMBERS_FILE):
        with open(_MEMBERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _LAMDA_MEMBERS.update(data.get("members", []))
    else:
        _LAMDA_MEMBERS.update(_FACULTY_EN_MAP.keys())

    # 构建英文名集合（教师的英文名 + LAMDA网页URL中的缩写）
    for en_names in _FACULTY_EN_MAP.values():
        for name in en_names:
            _ENGLISH_NAMES.add(name.lower())


def is_lamda_author(authors: list[str]) -> bool:
    """检查作者列表中是否有LAMDA成员（中英文名均支持）"""
    _load_members()
    for author in authors:
        name = author.strip()

        # 精确匹配中文名
        if name in _LAMDA_MEMBERS:
            return True

        # 英文名匹配（规范化处理后比较）
        name_lower = name.lower().replace(".", ". ").replace("  ", " ").strip()
        for en_name in _ENGLISH_NAMES:
            en_lower = en_name.lower()
            # 完全匹配
            if name_lower == en_lower:
                return True
            # 缩写形式匹配（如 "Zhou Z" 匹配 "Zhou Z.-H."）
            if ".-" in en_lower:
                # 提取姓+首字母 "zhou z"
                parts = en_lower.replace(".-", "").split()
                if len(parts) >= 2:
                    short = f"{parts[0]} {parts[1][0]}"
                    if name_lower.startswith(short):
                        return True

        # 通用匹配：检查作者英文名中是否有LAMDA成员的中文姓氏
        # 例如 "Zhi-Hua Zhou" 中包含姓氏 "Zhou"
        # 太宽泛会导致误匹配，仅在同时有NJU标识时使用（在check_nju中处理）

    return False


def is_lamda_text(text: str) -> bool:
    """检查文本中是否出现LAMDA成员姓名（含中英文）"""
    _load_members()
    # 中文名匹配（>=3字符避免短名误匹配）
    for member in _LAMDA_MEMBERS:
        if len(member) >= 3 and member in text:
            return True
    # 英文名匹配
    text_lower = text.lower()
    for en_name in _ENGLISH_NAMES:
        if en_name.lower() in text_lower:
            return True
    return False


def check_nju(text: str, authors: list[str] = None) -> bool:
    """
    综合LAMDA成员+NJU判断，3层策略:
    1. 作者精确匹配 LAMDA 名单 → 极高置信度 (LAMDA author)
    2. 文本含 LAMDA成员(中/英) + NJU标识 → 高置信度
    3. 文本含 NJU标识 (排除南邮/南理工等) → 中置信度
    """
    text_lower = text.lower()

    # ── 排除非南大 ──
    if "nanjing university of posts" in text_lower:
        return False
    if "nanjing university of science" in text_lower:
        return False
    if "nanjing university of information" in text_lower:
        return False

    nju_markers = ["nanjing university", "nju", "南京大学", "南大", "lamda"]

    # 排除含 "njut" / "njust" 等非南大缩写（除非明确有 "nanjing university" 标识）
    nju_exclude = ["njust", "njut", "njupt"]
    if not any(m in text_lower for m in ["nanjing university"]):
        for ex in nju_exclude:
            if ex in text_lower:
                return False
    has_nju = any(m in text_lower for m in nju_markers)

    # 策略1: LAMDA 作者直接命中
    if authors and is_lamda_author(authors):
        return True

    # 策略2: LAMDA成员名 + NJU标识
    if has_nju and is_lamda_text(text):
        return True

    # 策略3: NJU标识
    if has_nju:
        return True

    return False


def get_member_count() -> int:
    """返回LAMDA成员数量"""
    _load_members()
    return len(_LAMDA_MEMBERS)


def get_english_name_count() -> int:
    """返回英文名映射数量"""
    _load_members()
    return len(_ENGLISH_NAMES)
