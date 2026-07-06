"""MCP 客户端模块。

连接外部 MCP 服务器，获取其工具并转换为 LangChain Tool 格式，
让 Agent 可以像使用内置工具一样调用 MCP 工具。

容错机制：
- 逐服务器连接：单个 MCP server 失败不影响其他 server
- 超时保护：每个 server 连接最多等待 10 秒
- 降级策略：连接失败的 server 跳过，不阻塞 Agent 启动

配置格式（data/user_settings.json）:
    "mcp_servers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "transport": "stdio"
        }
    }
"""

import asyncio
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from server.logging_config import get_logger

logger = get_logger(__name__)

# 单个 MCP server 连接超时（秒）
_MCP_CONNECT_TIMEOUT = 10


async def _load_single_server_tools(name: str, server_cfg: dict) -> list:
    """连接单个 MCP server 并加载其工具。

    独立超时和异常处理：单个 server 失败不影响其他 server。

    Args:
        name: server 名称
        server_cfg: {command, args, transport} 或 {url, transport}

    Returns:
        该 server 的工具列表（失败时返回空列表）
    """
    try:
        client = MultiServerMCPClient({name: server_cfg})
        tools = await asyncio.wait_for(
            client.get_tools(),
            timeout=_MCP_CONNECT_TIMEOUT,
        )
        logger.info("MCP server '%s' 加载了 %d 个工具: %s",
                     name, len(tools), [t.name for t in tools])
        return tools
    except asyncio.TimeoutError:
        logger.warning("MCP server '%s' 连接超时（%ds），跳过", name, _MCP_CONNECT_TIMEOUT)
        return []
    except Exception as exc:
        logger.warning("MCP server '%s' 连接失败: %s，跳过", name, exc)
        return []


async def load_mcp_tools(mcp_servers: dict) -> list:
    """从配置的 MCP 服务器加载所有工具。

    逐服务器连接，单个失败不影响整体。
    全部失败时返回空列表，Agent 仍能正常使用内置工具。

    Args:
        mcp_servers: {name: {command, args, transport}} 配置

    Returns:
        LangChain Tool 列表（空列表表示无 MCP 工具或全部连接失败）
    """
    if not mcp_servers:
        return []

    # 转换为 MultiServerMCPClient 需要的格式
    servers = {}
    for name, cfg in mcp_servers.items():
        transport = cfg.get("transport", "stdio")
        if transport == "stdio":
            servers[name] = {
                "command": cfg["command"],
                "args": cfg.get("args", []),
                "transport": "stdio",
            }
        elif transport == "sse":
            servers[name] = {
                "url": cfg["url"],
                "transport": "sse",
            }

    # 逐服务器连接：并发的服务器都连，但各自独立容错
    tasks = [
        _load_single_server_tools(name, server_cfg)
        for name, server_cfg in servers.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 合并所有成功加载的工具
    all_tools = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            server_name = list(servers.keys())[i]
            logger.warning("MCP server '%s' 异常: %s", server_name, result)
        elif isinstance(result, list):
            all_tools.extend(result)

    logger.info("MCP 工具加载完成: 共 %d 个工具", len(all_tools))
    return all_tools
