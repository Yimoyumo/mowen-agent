# 云服务器 Docker 部署

> 状态：✅ 方案已设计完成
> 创建时间：2026-07-07
> 更新时间：2026-07-08
> 服务器配置：2核 4G

## 资源约束

2核 4G 比较紧张，需要精打细算：

| 组件 | 内存占用 | 说明 |
|------|---------|------|
| 系统 + Docker | ~500MB | 操作系统 + Docker 守护进程 |
| 项目容器（FastAPI） | ~300MB | Python + LangChain + 依赖 |
| 前端（Nginx 静态） | ~20MB | Nginx 托管 |
| Chroma 向量库 | ~200MB | 取决于知识库大小 |
| 沙盒容器 × 1 | ~100-512MB | Agent 执行任务时才创建 |
| **合计（空闲）** | ~1GB | 项目 + 前端 + 向量库 |
| **合计（1个沙盒活跃）** | ~1.5-2GB | 空闲 + 沙盒 |
| **合计（2个沙盒并发）** | ~2-2.5GB | 接近极限 |

### 针对方案的建议调整

| 配置项 | 原值 | 建议值 | 原因 |
|-------|------|-------|------|
| `_SANDBOX_MEMORY` | 512m | **256m** | 省内存，pandas 10万行仍可跑 |
| `_MAX_SANDBOXES` | 10 | **3** | 2核4G 最多支撑 2-3 个并发 |
| `_SANDBOX_IDLE_TIMEOUT` | 1800s(30min) | **900s(15min)** | 更快释放内存 |
| Chroma | 内嵌模式 | 保持内嵌 | 单机不折腾分离 |
| 前端 | — | Nginx 静态托管 | 不跑 Node，省内存 |

## 问题

项目本身打包成 Docker 镜像部署到云服务器后，沙盒（Docker 容器）还能不能用？

本质是 **Docker-in-Docker** 问题：项目容器里需要创建/管理沙盒容器。

## 解决方案：挂载 Docker Socket（推荐）

不需要 DinD，让项目容器**共享宿主机的 Docker 引擎**。

### docker-compose.yml 示例

```yaml
services:
  app:
    image: mowen-app:latest
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # 关键！共享宿主机 Docker
      - ./data:/app/data                          # 配置/数据目录
      - ./downloads:/app/downloads                # 沙盒导出文件目录
      - ./uploads:/app/uploads                     # 用户上传文件目录
      - ./vectorstore:/app/vectorstore             # Chroma 向量库
      - ./skills:/app/skills                       # 技能目录
      - ./.agents/skills:/app/.agents/skills       # 项目级技能
    restart: unless-stopped
```

### 注意事项

| 事项 | 说明 |
|------|------|
| **沙盒镜像** | `mowen-sandbox:latest` 需在宿主机上提前构建好，不在项目镜像内 |
| **路径映射** | `downloads/`、`uploads/` 必须挂载，否则 `docker cp` 导出文件找不到 |
| **网络** | 沙盒容器和项目容器都在宿主机网络上，互不影响 |
| **权限** | socket 挂载需 docker 组权限，云服务器 root 运行无问题 |
| **前端** | 前端单独构建为静态文件，用 Nginx 托管或嵌入项目容器 |

### 部署流程（预估）

#### 方式一：本地构建镜像 → 传到服务器（✅ 推荐）

2核4G 服务器直接构建会很慢且容易遇到网络超时，在本地构建好再传过去。

```bash
# === 本地操作 ===

# 1. 本地构建好两个镜像
docker build -t mowen-sandbox:latest -f Dockerfile.sandbox .
docker build -t mowen-app:latest -f Dockerfile.app .

# 2. 导出为压缩 tar 文件
docker save mowen-sandbox:latest | gzip > mowen-sandbox.tar.gz   # ~800MB-1GB
docker save mowen-app:latest | gzip > mowen-app.tar.gz            # ~200-300MB

# 3. 传到服务器
scp mowen-sandbox.tar.gz mowen-app.tar.gz root@服务器IP:/root/

# === 服务器操作 ===

# 4. 加载镜像
docker load < mowen-sandbox.tar.gz
docker load < mowen-app.tar.gz

# 5. docker-compose 启动
docker compose up -d
```

#### 方式二：服务器直接构建（❌ 不推荐）

```bash
# 把代码传上去
scp -r /root/rag-agent-learning root@服务器IP:/root/

# 服务器上构建
docker build -t mowen-sandbox:latest -f Dockerfile.sandbox .
docker build -t mowen-app:latest -f Dockerfile.app .

docker compose up -d
```

> 缺点：2核4G 构建慢、镜像源超时风险高、下载依赖占用带宽

#### 两种方式对比

| | 本地构建传输 | 服务器直接构建 |
|---|---|---|
| 速度 | ✅ 快（本地性能好） | ❌ 慢（2核4G 编译吃力） |
| 带宽 | 传一次压缩包 | 构建时反复下载依赖 |
| 网络问题 | ✅ 本地源稳 | ⚠️ 可能超时 |
| 后续更新 | 每次改代码都要重传镜像 | git pull 就能重建 |
| 适用场景 | 正式部署 | 开发调试 |

## 不推荐的方案

- **真 DinD（privileged: true）**：安全风险大、性能差、镜像翻倍、容易出怪问题

## 已实现的部署文件

| 文件 | 说明 |
|------|------|
| `Dockerfile.app` | 项目镜像：多阶段构建（前端 build + 后端 + Nginx） |
| `Dockerfile.sandbox` | 沙盒镜像（预装 Python 包 + 系统工具） |
| `docker-compose.yml` | 编排配置（Docker Socket 挂载 + 数据卷 + 资源限制） |
| `deploy/nginx.conf` | Nginx 配置（SPA 路由 + API 反代 + SSE 支持） |
| `deploy/start.sh` | 启动脚本（同时运行 Nginx + Uvicorn） |
| `deploy/build-and-deploy.sh` | 一键部署脚本（本地构建 -> 传输 -> 启动） |
| `deploy/server-init.sh` | 服务器端初始化脚本（装 Docker + 创建目录） |
| `.dockerignore` | Docker 构建排除规则 |

### 架构

```
                    :80
                     │
              ┌──────┴──────┐
              │   Nginx     │  (容器内)
              │  ┌────────┐ │
              │  │ 静态文件 │ │  /usr/share/nginx/html (Vue SPA)
              │  └────────┘ │
              │  ┌────────┐ │
              │  │ /api/  │─┼──> 127.0.0.1:8000 (Uvicorn)
              │  └────────┘ │  (SSE 流式: proxy_buffering off)
              └─────────────┘
                     │
              ┌──────┴──────┐
              │  FastAPI     │  (容器内)
              │  Uvicorn     │
              │  LangGraph   │
              └──────┬───────┘
                     │ docker.sock (宿主机)
              ┌──────┴──────┐
              │  沙盒容器    │  mowen-sandbox:latest
              │  (按需创建)  │  256MB / 15min 超时
              └─────────────┘
```

### 资源调整（已应用）

`server/agent/sandbox.py` 已按 2核4G 调整：

| 配置项 | 原值 | 新值 |
|-------|------|------|
| `_SANDBOX_MEMORY` | 512m | **256m** |
| `_MAX_SANDBOXES` | 10 | **3** |
| `_SANDBOX_IDLE_TIMEOUT` | 1800s | **900s** |

### 一键部署

```bash
# 本地执行（需要能 ssh 到服务器）
chmod +x deploy/build-and-deploy.sh
./deploy/build-and-deploy.sh 123.45.67.89

# 或手动分步：
# 1. 本地构建
docker build -t mowen-app:latest -f Dockerfile.app .
docker build -t mowen-sandbox:latest -f Dockerfile.sandbox .

# 2. 传输
docker save mowen-app:latest | gzip > /tmp/mowen-app.tar.gz
docker save mowen-sandbox:latest | gzip > /tmp/mowen-sandbox.tar.gz
scp /tmp/mowen-*.tar.gz root@服务器IP:/tmp/

# 3. 服务器加载 + 启动
ssh root@服务器IP 'bash -s' < deploy/server-init.sh
scp docker-compose.yml root@服务器IP:/root/mowen-deploy/
ssh root@服务器IP 'cd /root/mowen-deploy && docker compose up -d'
```

### 日常运维

```bash
# 查看日志
docker compose logs -f

# 重启
docker compose restart

# 更新（本地重新构建 -> 传输 -> 加载 -> 重启）
./deploy/build-and-deploy.sh 服务器IP

# 进入容器调试
docker exec -it mowen-app bash
```
