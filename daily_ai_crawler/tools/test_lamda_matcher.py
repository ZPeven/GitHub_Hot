import sys
sys.path.insert(0, "..")
from processors.lamda_matcher import check_nju, is_lamda_author, get_member_count, get_english_name_count

print(f"Members: {get_member_count()}, EN names: {get_english_name_count()}")

# Test with English author names
tests = [
    (["Zhi-Hua Zhou", "Yang Yu"], True, "LAMDA teachers full"),
    (["Wei Gao", "Ming Li"], True, "LAMDA teachers full"),
    (["John Smith", "Alice Johnson"], False, "non-LAMDA"),
    (["Z.-H. Zhou", "Yuan Jiang"], True, "abbreviated + full"),
    (["Zhou Z.-H.", "Jiang Y."], True, "last-first pattern"),
    ([], False, "empty authors"),
    (["Han-Jia Ye"], True, "Ye HJ full"),
    (["De-Chuan Zhan", "Li-Jun Zhang"], True, "Zhan + Zhang"),
    (["Chao Qian"], True, "Chao Qian"),
]

for authors, expected, desc in tests:
    result = is_lamda_author(authors)
    status = "OK" if result == expected else "FAIL"
    print(f"  [{status}] {desc}: {result} (expected {expected})")

# Test check_nju
print()
nju_tests = [
    ("ML paper by Zhi-Hua Zhou from LAMDA NJU", ["Zhi-Hua Zhou"], True, "Zhou with LAMDA text"),
    ("Physics paper from Nanjing University", [], True, "NJU text only"),
    ("Paper from NUPT Nanjing", [], False, "excluded NUPT"),
    ("Paper from NJU with Han-Jia Ye", ["Han-Jia Ye"], True, "YE with NJU"),
    ("Research from NJUST", [], False, "excluded NJUST"),
]

for text, authors, expected, desc in nju_tests:
    result = check_nju(text, authors)
    status = "OK" if result == expected else "FAIL"
    print(f"  [{status}] {desc}: {result} (expected {expected})")
