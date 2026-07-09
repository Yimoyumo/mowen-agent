# ==================== 构建阶段：前端 ====================
FROM node:20-slim AS frontend-builder

WORKDIR /build

# 先复制 package 文件，利用 Docker 缓存
COPY frontend/package.json frontend/package-lock.json* ./

# 使用淘宝镜像加速
RUN npm config set registry https://registry.npmmirror.com && \
    npm ci || npm install

# 复制源码并构建
COPY frontend/ .
RUN npm run build-only

# ==================== 运行阶段：后端 + Nginx ====================
FROM python:3.13-slim

# 系统依赖 + Nginx + Node.js（MCP 工具需要 npx）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    curl \
    ca-certificates \
    nodejs \
    npm \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# pip 阿里云镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set global.trusted-host mirrors.aliyun.com

WORKDIR /app

# 先装依赖（只用直接依赖，传递依赖由 pip 自动解决）
COPY pyproject.toml uv.lock ./
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set global.trusted-host mirrors.aliyun.com && \
    for i in 1 2 3 4 5; do \
        pip install --no-cache-dir --default-timeout=300 \
        "langchain>=1.3" "langchain-community>=0.3" \
        "langchain-classic>=1.0" "langchain-text-splitters>=1.1" \
        "langchain-chroma>=1.1" "chromadb>=1.5" \
        "pypdf>=5.0" "python-docx>=1.1" \
        "httpx>=0.28" \
        "fastapi>=0.139" "uvicorn>=0.49" \
        "langchain-deepseek>=1.1" "langgraph>=1.2" \
        "tavily-python>=0.7" "python-multipart>=0.0" \
        "docker>=7.1" "langchain-mcp-adapters>=0.3" "mcp>=1.28" \
        "langchain-openai>=1.3" "apscheduler>=3.11" && break || \
        echo "pip 安装重试 $i/5..." && sleep 5; \
    done && \
    python3 -c "import uvicorn, fastapi, langchain, langgraph; print('依赖验证通过')"

# 安装 Playwright Chromium（@playwright/mcp 需要）
# npm 用淘宝镜像，浏览器从官方 CDN 下载（淘宝镜像不含 Chrome for Testing）
RUN npm install -g @playwright/mcp && \
    for i in 1 2 3; do \
        unset PLAYWRIGHT_DOWNLOAD_HOST && \
        npx @playwright/mcp install-browser chrome-for-testing && break || \
        echo "Playwright 安装重试 $i/3..." && sleep 5; \
    done

# 复制项目代码
COPY . .

# 复制前端构建产物
COPY --from=frontend-builder /build/dist /usr/share/nginx/html

# Nginx 配置
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
# 移除默认站点，避免冲突
RUN rm -f /etc/nginx/sites-enabled/default

# 创建必要目录
RUN mkdir -p /app/data /app/downloads /app/uploads /app/logs /app/vectorstore

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 启动脚本：同时运行 Nginx 和 Uvicorn
COPY deploy/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
