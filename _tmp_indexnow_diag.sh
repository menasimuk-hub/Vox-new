#!/bin/bash
set -e
cd /www/voxbulk/voxbulk.com/frontend
KEY=$(curl -s http://127.0.0.1:8000/frontpage/seo/indexnow-key | sed -n 's/.*"key":"\([^"]*\)".*/\1/p')
echo "KEY=$KEY"
echo "=== direct api ==="
curl -s "http://127.0.0.1:8000/frontpage/seo/indexnow-key"; echo
echo "=== vite local ==="
curl -s -w "\nHTTP:%{http_code}\n" "http://127.0.0.1:5173/${KEY}.txt"
echo "=== public ==="
curl -s -w "\nHTTP:%{http_code}\n" "https://voxbulk.com/${KEY}.txt"
echo "=== grep build ==="
rg -n "indexnow-key|127.0.0.1:8000" dist/server -g '*.js' | head -20
echo "=== preview log tail ==="
tail -30 /tmp/voxbulk-public.log 2>/dev/null || tail -30 /tmp/voxbulk-public-qusay.log 2>/dev/null || true
