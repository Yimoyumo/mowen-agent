#!/bin/bash
# ====================================================
# 墨问 AI 助手 - 一键部署脚本
# 适用于：2核4G 云服务器
# 方式：本地构建镜像 -> 传到服务器 -> docker compose up
# ====================================================

set -e

# ---- 配置 ----
SERVER_IP="${1:-}"
SERVER_USER="${2:-root}"
PROJECT_DIR="/root/rag-agent-learning"
DEPLOY_DIR="/root/mowen-deploy"

echo "=========================================="
echo "  墨问 AI 助手 - 部署脚本"
echo "=========================================="

# ---- Step 0: 检查参数 ----
if [ -z "$SERVER_IP" ]; then
    echo "用法: ./deploy/build-and-deploy.sh <服务器IP> [用户名]"
    echo "示例: ./deploy/build-and-deploy.sh 123.45.67.89"
    echo "      ./deploy/build-and-deploy.sh 123.45.67.89 root"
    exit 1
fi

echo "目标服务器: $SERVER_USER@$SERVER_IP"
echo ""

# ---- Step 1: 本地构建前端 ----
echo "[1/6] 构建前端..."
cd "$PROJECT_DIR/frontend"
npm run build-only
echo "  ✓ 前端构建完成"

# ---- Step 2: 构建 Docker 镜像 ----
echo "[2/6] 构建 mowen-app 镜像..."
cd "$PROJECT_DIR"
docker build -t mowen-app:latest -f Dockerfile.app .
echo "  ✓ mowen-app 镜像构建完成"

# 检查沙盒镜像是否存在，不存在则构建
if ! docker image inspect mowen-sandbox:latest >/dev/null 2>&1; then
    echo "[2.5] 构建 mowen-sandbox 镜像..."
    docker build -t mowen-sandbox:latest -f Dockerfile.sandbox .
    echo "  ✓ mowen-sandbox 镜像构建完成"
else
    echo "  ✓ mowen-sandbox 镜像已存在，跳过"
fi

# ---- Step 3: 导出镜像 ----
echo "[3/6] 导出镜像为压缩包..."
docker save mowen-app:latest | gzip > /tmp/mowen-app.tar.gz
docker save mowen-sandbox:latest | gzip > /tmp/mowen-sandbox.tar.gz
APP_SIZE=$(du -h /tmp/mowen-app.tar.gz | cut -f1)
SANDBOX_SIZE=$(du -h /tmp/mowen-sandbox.tar.gz | cut -f1)
echo "  ✓ mowen-app.tar.gz ($APP_SIZE)"
echo "  ✓ mowen-sandbox.tar.gz ($SANDBOX_SIZE)"

# ---- Step 4: 传到服务器 ----
echo "[4/6] 传输镜像到服务器..."
scp /tmp/mowen-app.tar.gz /tmp/mowen-sandbox.tar.gz "$SERVER_USER@$SERVER_IP:/tmp/"
scp docker-compose.yml "$SERVER_USER@$SERVER_IP:$DEPLOY_DIR/"
echo "  ✓ 传输完成"

# ---- Step 5: 服务器加载镜像 ----
echo "[5/6] 服务器加载镜像..."
ssh "$SERVER_USER@$SERVER_IP" "
    mkdir -p $DEPLOY_DIR
    docker load < /tmp/mowen-app.tar.gz
    docker load < /tmp/mowen-sandbox.tar.gz
    rm -f /tmp/mowen-app.tar.gz /tmp/mowen-sandbox.tar.gz
    echo '  ✓ 镜像加载完成'
"

# ---- Step 6: 启动 ----
echo "[6/6] 启动服务..."
ssh "$SERVER_USER@$SERVER_IP" "
    cd $DEPLOY_DIR
    # 创建数据目录
    mkdir -p data downloads uploads vectorstore logs skills .agents/skills
    # 启动
    docker compose down 2>/dev/null || true
    docker compose up -d
    sleep 3
    docker compose ps
    echo ''
    echo '=== 部署完成 ==='
    echo '访问: http://$SERVER_IP'
    echo '日志: docker compose logs -f'
"

echo ""
echo "=========================================="
echo "  ✓ 部署完成！"
echo "  访问: http://$SERVER_IP"
echo "  日志: ssh $SERVER_USER@$SERVER_IP 'cd $DEPLOY_DIR && docker compose logs -f'"
echo "=========================================="
