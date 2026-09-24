#!/bin/bash
# 只读侦察：判据库怎么被找到的、标准引用清单里有什么字段（**不修改任何文件**）
echo '=== 服务进程的环境变量里有没有 EIA_CRITERIA_DIR ==='
tr '\0' '\n' < /proc/$(cat /home/test/xishu_qingyu_serve/qa_8011.pid)/environ 2>/dev/null | grep -i 'EIA_\|CRITERIA' || echo '（进程环境里没有）'

echo
echo '=== 启动脚本里怎么设的 ==='
grep -n 'EIA_\|CRITERIA\|判据' /home/test/安全重启8011.sh 2>/dev/null | head -10
echo '--- 其他可能的启动脚本 ---'
ls /home/test/*.sh 2>/dev/null | head -20

echo
echo '=== 标准引用清单.json 结构（只看字段与样例，不打印全文）==='
cat > /tmp/_看标准.py <<'PY'
import json
p = '/data/eia_report_gen/判据库/标准引用清单.json'
j = json.load(open(p, encoding='utf-8'))
print('顶层键:', list(j))
print('来源:', j.get('来源'))
print('性质:', str(j.get('性质'))[:200])
print('标准数:', j.get('标准数'))
print('生成:', str(j.get('生成'))[:200])
std = j.get('标准')
print('标准类型:', type(std).__name__, len(std) if hasattr(std, '__len__') else '')
if isinstance(std, dict):
    ks = list(std)[:3]
    for k in ks:
        print(' 样例键:', k, '→', json.dumps(std[k], ensure_ascii=False)[:400])
elif isinstance(std, list):
    for it in std[:2]:
        print(' 样例:', json.dumps(it, ensure_ascii=False)[:400])
    # 看有没有"状态/废止/代替"这类字段
    keys = set()
    for it in std[:2000]:
        if isinstance(it, dict):
            keys |= set(it)
    print('全部字段名:', sorted(keys))
    for it in std:
        if isinstance(it, dict) and 'GB 3095' in json.dumps(it, ensure_ascii=False).replace('GB3095', 'GB 3095'):
            print(' GB3095 相关样例:', json.dumps(it, ensure_ascii=False)[:500])
            break
PY
/home/test/fagui_serve/.venv/bin/python /tmp/_看标准.py
