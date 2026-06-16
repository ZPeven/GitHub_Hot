import json

with open('lamda_members.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

teachers = ['周志华', '姜远', '高尉', '李宇峰', '王魏', '俞扬', '李武军', '钱超', '黎铭', '吴建鑫']
for t in teachers:
    status = 'YES' if t in data['all_names'] else 'MISSING'
    print(f'  {t}: {status}')
print(f'Total: {len(data["all_names"])} names')
