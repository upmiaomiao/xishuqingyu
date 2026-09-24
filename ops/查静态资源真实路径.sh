#!/usr/bin/env bash
# 只读：找出静态资源的真实 URL，并确认线上返回的是新版文件。
set -u
B=http://127.0.0.1:8011

echo "===== 1) /gen 页面引用的资源路径 ====="
curl -s "$B/gen" | grep -oE '(src|href)="[^"]+"' | head -12

echo
echo "===== 2) 首页引用的资源路径（问答页）====="
curl -s "$B/" | grep -oE '(src|href)="[^"]+"' | head -12

echo
echo "===== 3) 逐个 URL 看状态与特征串 ====="
probe() {
  local u="$1" s="$2" label="$3"
  local code size hit
  code=$(curl -s -o /tmp/_p.txt -w '%{http_code}' "$B$u")
  size=$(wc -c < /tmp/_p.txt)
  hit=$(grep -c -- "$s" /tmp/_p.txt || true)
  echo "  HTTP $code  ${size}B  特征串命中=$hit   $label  ($u)"
}

probe /static/gen_ui.js                 "isComposing"   "编制页输入法守卫"
probe /xishu_pipeline/static/gen_ui.js  "isComposing"   "（旧路径对照）"
probe /static/audit_ui.js               "au-na-note"    "审核界面不适用口径"
probe /static/audit_ui.css              "au-na-note"    "口径样式"
probe /static/js/main.js                "isComposing"   "问答页输入法守卫"
probe /frontend/js/main.js              "isComposing"   "（旧路径对照）"
probe /static/gen_ui.js                 "ge-prog-stage" "新建报告复位进度条"
