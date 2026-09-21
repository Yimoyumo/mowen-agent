# ==================== 构建阶段：前端 ====================
# Node 版本与 frontend/package.json 的 engines（^22.18.0 || >=24.12.0）保持一致，
# 旧版用的是 node:20，比项目要求低一个大版本，能否构建成功取决于镜像小版本。
FROM node:22-slim AS frontend-builder

WORKDIR /build

# 先复制依赖清单，利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 复制源码并构建
COPY frontend/ ./
RUN npm run build-only

# ==================== 运行阶段：后端 + Nginx ====================
FROM python:3.13-slim

# 系统依赖：Nginx（静态文件 + 反代）、curl（compose 健康检查用）、
# Node.js/npm（默认 MCP 配置里的 playwright-mcp / mcp-server-filesystem 都是 npm 包）
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        curl \
        ca-certificates \
        nodejs \
        npm \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python 依赖：严格按 uv.lock 安装 ----------
# 不再手写包名清单。手写清单会漏包：此前漏了 beautifulsoup4 / html2text / chardet，
# 容器里 fetch_webpage 与 Bing 搜索降级会直接 ImportError；而本地 dev 之所以正常，
# 是因为 beautifulsoup4 被 notebook → nbconvert 顺带装了进来（现已补进 pyproject）。
# 按锁文件安装还能避免版本漂移：旧写法用 >= 让 pip 取最新，镜像里 openai 从
# 2.44 跳到 3.16，跟本地测试过的组合不是一套。
#
# NOTEBOOK_ONLY_RE 剔除只服务本地 notebook 的依赖链（notebook/ipykernel 及其独占依赖）。
# notebook/ 已在 .dockerignore 中，镜像里没有任何代码 import 它。
# 重新生成：用 uv.lock 的依赖图求 notebook+ipykernel 的传递闭包，减去 pyproject
# 运行时依赖的闭包，剩下的包名即此列表；多列或漏列都不会让安装失败，只影响体积。
ENV NOTEBOOK_ONLY_RE="^(appnope|argon2-cffi|argon2-cffi-bindings|asttokens|async-lru|babel|bleach|comm|debugpy|decorator|defusedxml|executing|fastjsonschema|ipykernel|ipython|ipython-pygments-lexers|jedi|jinja2|json5|jupyter-builder|jupyter-client|jupyter-core|jupyter-events|jupyter-lsp|jupyter-server|jupyter-server-terminals|jupyterlab|jupyterlab-pygments|jupyterlab-server|markupsafe|matplotlib-inline|mistune|nbclient|nbconvert|nbformat|nest-asyncio2|notebook|notebook-shim|pandocfilters|parso|pexpect|platformdirs|prometheus-client|prompt-toolkit|psutil|ptyprocess|pure-eval|python-json-logger|pywinpty|pyzmq|send2trash|stack-data|terminado|tinycss2|tornado|traitlets|wcwidth|webencodings)=="

RUN pip install --no-cache-dir "uv==0.11.26" \
 && uv export --frozen --no-dev --no-emit-project -o /tmp/req.txt \
 && grep -vE "$NOTEBOOK_ONLY_RE" /tmp/req.txt > /tmp/req-app.txt \
 && uv pip install --system --no-cache --index-url https://pypi.org/simple -r /tmp/req-app.txt \
 && rm -f /tmp/req.txt /tmp/req-app.txt \
 && python -c "import uvicorn, fastapi, langchain, langgraph, bs4, html2text, chardet; print('依赖校验通过')"

# ---------- MCP 服务器 ----------
# 全局安装而非运行时 npx -y 临时下载：避免容器里 bin 链接丢失导致加载 0 工具。
# zod 是 @modelcontextprotocol/server-filesystem 的 ESM 解析依赖。
RUN for i in 1 2 3; do \
        npm install -g @playwright/mcp @modelcontextprotocol/server-filesystem zod && break || \
        echo "npm 全局安装重试 $i/3..." && sleep 5; \
    done \
 && test -f "$(npm prefix -g)/lib/node_modules/@playwright/mcp/package.json" \
 && test -f "$(npm prefix -g)/lib/node_modules/@modelcontextprotocol/server-filesystem/package.json" \
 && test -x "$(npm prefix -g)/bin/playwright-mcp" \
 && test -x "$(npm prefix -g)/bin/mcp-server-filesystem"

# Playwright Chromium：浏览器走官方 CDN，系统库走 Debian 官方源
RUN for i in 1 2 3; do \
        npx @playwright/mcp install-browser chrome-for-testing && break || \
        echo "Playwright 浏览器安装重试 $i/3..." && sleep 5; \
    done \
 && (npx playwright install-deps chromium \
     || echo "⚠️  install-deps 失败：浏览器系统库可能缺失，playwright MCP 会显示 0 工具")

# 复制项目代码
COPY . .

# 复制前端构建产物
COPY --from=frontend-builder /build/dist /usr/share/nginx/html

# Nginx 配置（SPA 回退 + /api 反代到 127.0.0.1:8000）
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
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
