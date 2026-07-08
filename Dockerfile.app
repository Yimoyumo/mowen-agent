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

# 先装依赖（利用缓存）
COPY pyproject.toml uv.lock ./
# 阿里云镜像 + 多次重试应对网络不稳定
RUN for i in 1 2 3 4 5; do \
        pip install --no-cache-dir --default-timeout=300 uv && break || \
        echo "uv 安装重试 $i/5..." && sleep 3; \
    done && \
    for i in 1 2 3 4 5; do \
        uv pip install --system --no-cache \
        --index-url https://mirrors.aliyun.com/pypi/simple \
        --default-timeout=300 \
        "langchain==1.3.11" "langchain-core==1.4.8" "langchain-community==0.3.31" \
        "langchain-classic==1.0.8" "langchain-text-splitters==1.1.2" \
        "faiss-cpu==1.14.3" "langchain-chroma==1.1.0" "chromadb==1.5.9" \
        "zhipuai==2.1.5.20250825" "httpx==0.28.1" "httpx-sse==0.4.3" \
        "pyjwt==2.13.0" "cachetools==7.1.4" \
        "fastapi==0.139.0" "uvicorn==0.49.0" \
        "langchain-deepseek==1.1.0" "langgraph==1.2.7" \
        "tavily-python==0.7.26" "python-multipart==0.0.32" \
        "docker==7.1.0" "langchain-mcp-adapters==0.3.0" "mcp==1.28.1" \
        "langchain-openai==1.3.3" "apscheduler==3.11.3" && break || \
        echo "依赖安装重试 $i/5..." && sleep 5; \
    done

# 安装 Playwright Chromium（@playwright/mcp 需要）
# 用淘宝镜像加速下载，只装 chromium
RUN npx -y playwright@latest install --with-deps chromium

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
