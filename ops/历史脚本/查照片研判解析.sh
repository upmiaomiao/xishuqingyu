#!/bin/bash
echo "=== 1. photo_messages 提示词 ==="
grep -n "def photo_messages" -A 60 /home/test/xishu_qingyu_serve/xishu_pipeline/prompts.py

echo
echo "=== 2. extract_json_object 实现 ==="
grep -rn "def extract_json_object" -A 40 /home/test/xishu_qingyu_serve/xishu_pipeline/*.py

echo
echo "=== 3. render_photo_report 期望的字段 ==="
grep -rn "def render_photo_report" -A 45 /home/test/xishu_qingyu_serve/xishu_pipeline/postprocess.py
