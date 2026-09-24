import json
import re

path = '/home/test/convert_validation_server_v3.py'
with open(path) as f:
    content = f.read()

# Replace the DecimalEncoder class
old_encoder = '''class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)'''

new_encoder = '''class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        from datetime import date, datetime, time
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, time):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)'''

content = content.replace(old_encoder, new_encoder)

with open(path, 'w') as f:
    f.write(content)

print('Patched successfully')
