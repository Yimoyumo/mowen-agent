#!/bin/bash
# 启动脚本 - 同时运行 Nginx 和 Uvicorn
# Nginx 处理前端静态文件 + 反向代理 API
# Uvicorn 运行 FastAPI 后端

set -e

echo "=== 启动墨问 AI 助手 ==="

# 启动 Nginx（前台模式不需要 daemon）
echo "[1/2] 启动 Nginx..."
nginx -g 'daemon off;' &

# 启动 Uvicorn
echo "[2/2] 启动 Uvicorn (FastAPI)..."
cd /app
exec python3 -m uvicorn api:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1 \
    --no-access-log
