#!/bin/bash
# ====================================================
# 墨问 AI 助手 - 服务器端初始化脚本
# 在云服务器上运行，安装 Docker + 加载镜像 + 启动
# 用法: ssh root@服务器IP 'bash -s' < deploy/server-init.sh
# ====================================================

set -e

echo "=== 墨问 AI 助手 - 服务器初始化 ==="

DEPLOY_DIR="/root/mowen-deploy"

# ---- Step 1: 检查 Docker ----
echo "[1/5] 检查 Docker..."
if ! command -v docker &>/dev/null; then
    echo "  安装 Docker..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    echo "  ✓ Docker 安装完成"
else
    echo "  ✓ Docker 已安装: $(docker --version)"
fi

# 检查 docker compose
if ! docker compose version &>/dev/null; then
    echo "  ✗ docker compose 不可用，请安装 docker-compose-plugin"
    exit 1
fi

# ---- Step 2: 创建部署目录 ----
echo "[2/5] 创建部署目录..."
mkdir -p "$DEPLOY_DIR"/{data,downloads,uploads,vectorstore,logs}
mkdir -p "$DEPLOY_DIR"/skills
mkdir -p "$DEPLOY_DIR"/.agents/skills
echo "  ✓ 目录创建完成: $DEPLOY_DIR"

# ---- Step 3: 加载镜像 ----
echo "[3/5] 加载镜像..."
if [ -f /tmp/mowen-app.tar.gz ]; then
    echo "  加载 mowen-app..."
    docker load < /tmp/mowen-app.tar.gz
    rm -f /tmp/mowen-app.tar.gz
    echo "  ✓ mowen-app 加载完成"
else
    echo "  ⚠ mowen-app.tar.gz 不存在，跳过（可能已加载）"
fi

if [ -f /tmp/mowen-sandbox.tar.gz ]; then
    echo "  加载 mowen-sandbox..."
    docker load < /tmp/mowen-sandbox.tar.gz
    rm -f /tmp/mowen-sandbox.tar.gz
    echo "  ✓ mowen-sandbox 加载完成"
else
    echo "  ⚠ mowen-sandbox.tar.gz 不存在，跳过"
fi

# ---- Step 4: 验证镜像 ----
echo "[4/5] 验证镜像..."
docker image inspect mowen-app:latest >/dev/null 2>&1 && echo "  ✓ mowen-app:latest" || echo "  ✗ mowen-app:latest 缺失"
docker image inspect mowen-sandbox:latest >/dev/null 2>&1 && echo "  ✓ mowen-sandbox:latest" || echo "  ✗ mowen-sandbox:latest 缺失"

# ---- Step 5: 提示下一步 ----
echo "[5/5] 下一步..."
echo ""
echo "  将 docker-compose.yml 放到 $DEPLOY_DIR/，然后："
echo "    cd $DEPLOY_DIR"
echo "    docker compose up -d"
echo ""
echo "  查看日志:"
echo "    docker compose logs -f"
echo ""
echo "=== 初始化完成 ==="
