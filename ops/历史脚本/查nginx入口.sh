#!/bin/bash
PW="Cecepd@123456"
echo "=== 1. nginx 配置里指向 8011 的地方 ==="
sudo -S grep -rn "8011\|8012\|8013\|proxy_pass\|server_name\|listen " /etc/nginx/ 2>/dev/null <<< "$PW" | grep -vE '^\s*#' | head -60

echo
echo "=== 2. nginx 是否在 docker 里 ==="
ps -o pid,cmd -p 229179
sudo -S ls -l /proc/229179/cwd 2>/dev/null <<< "$PW"

echo
echo "=== 3. docker 开机自启 ==="
systemctl is-enabled docker 2>&1
systemctl is-active docker 2>&1

echo
echo "=== 4. 通过 80 端口访问站点 ==="
for p in / /health /kg/stats /gen /audit; do
  printf "http  %-12s -> %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1$p)"
done
echo "--- 80 端口首页前 300 字 ---"
curl -s -m 10 http://127.0.0.1/ | head -c 300
echo
echo "--- 80 端口 /health ---"
curl -s -m 10 http://127.0.0.1/health | head -c 300
echo
echo "--- Host 头: 10.201.31.10 ---"
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -m 10 -H 'Host: 10.201.31.10' http://127.0.0.1/

echo
echo "=== 5. 443 证书 ==="
echo | openssl s_client -connect 127.0.0.1:443 -servername 10.201.31.10 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>/dev/null || echo "  取证书失败"

echo
echo "=== 6. 监听全清单（对外可达的）==="
ss -ltn 2>/dev/null | awk 'NR==1 || $4 !~ /^127\./'
