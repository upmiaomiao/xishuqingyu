import sys
sys.path.insert(0, '/home/test')
sys.path.insert(0, '/home/test/wenshu_agent/code')

from convert_validation_server import read_xlsx, clean_sql, execute_sql

records = read_xlsx('/home/test/validation_test_set.xlsx')
print(f'Total records: {len(records)}')

# Test first 3 records
for r in records[:3]:
    question = r.get('问题', '').strip()
    main_sql = clean_sql(r.get('使用SQL', '').strip())
    rid = r.get('问题序号', '')
    print(f'\nID: {rid}')
    print(f'Q: {question[:60]}...')
    print(f'SQL length: {len(main_sql)}')
    
    result = execute_sql(main_sql)
    err = result['error'][:80] if result['error'] else None
    print(f'Result: ok={result["ok"]}, rows={result["row_count"]}, error={err}')
