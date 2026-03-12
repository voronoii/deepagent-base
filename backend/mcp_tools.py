"""MCP (Model Context Protocol) tool manager.

Reads mcp_config.json, connects to enabled MCP servers
(stdio, SSE, and Streamable HTTP transports),
and wraps their tools as LangChain StructuredTool instances for use in agents.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Any
from urllib.parse import urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from pydantic import create_model, Field
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "mcp_config.json"


class MCPToolManager:
    """Manages connections to MCP servers and provides LangChain-compatible tools.

    Usage::

        manager = MCPToolManager()
        await manager.initialize()       # connect to all enabled servers
        tools = manager.get_tools()       # list[StructuredTool]
        ...
        await manager.shutdown()          # close all connections
    """

    def __init__(self, config_path: str | Path = CONFIG_PATH):
        self.config_path = Path(config_path)
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: list[StructuredTool] = []
        self._initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to all enabled MCP servers and load their tools."""
        if self._initialized:
            return

        config = self._load_config()
        servers = config.get("servers", [])
        enabled = [s for s in servers if s.get("enabled", False)]

        if not enabled:
            logger.info("No MCP servers enabled in %s", self.config_path)
            self._initialized = True
            return

        logger.info("Connecting to %d MCP server(s)...", len(enabled))

        for server_config in enabled:
            try:
                await self._connect_server(server_config)
            except Exception as e:
                logger.warning(
                    "Failed to connect to MCP server '%s': %s",
                    server_config.get("name", "unknown"),
                    e,
                )

        logger.info(
            "MCP initialization complete: %d tool(s) loaded", len(self._tools)
        )
        self._initialized = True

    def get_tools(self) -> list[StructuredTool]:
        """Return all loaded LangChain-compatible tools."""
        return list(self._tools)

    async def check_health(self) -> list[dict]:
        """Check health of all configured MCP servers.

        Returns a list of dicts, one per server:
            name, enabled, transport, url, status, latency_ms, tools, error
        """
        config = self._load_config()
        results = []

        for server_cfg in config.get("servers", []):
            name = server_cfg.get("name", "unknown")
            enabled = server_cfg.get("enabled", False)
            transport = server_cfg.get("transport", "stdio")
            url = server_cfg.get("url", "")
            description = server_cfg.get("description", "")

            if os.environ.get("DOCKER_ENV") and "url_docker" in server_cfg:
                url = server_cfg["url_docker"]

            entry = {
                "name": name,
                "enabled": enabled,
                "transport": transport,
                "url": url,
                "description": description,
                "status": "disabled",
                "latency_ms": None,
                "tools": [],
                "error": None,
            }

            if not enabled:
                results.append(entry)
                continue

            # Check if we have an active session
            if name in self._sessions:
                t0 = time.monotonic()
                try:
                    tools_result = await self._sessions[name].list_tools()
                    latency = (time.monotonic() - t0) * 1000
                    entry["status"] = "online"
                    entry["latency_ms"] = round(latency, 1)
                    entry["tools"] = [
                        {"name": t.name, "description": t.description or ""}
                        for t in tools_result.tools
                    ]
                except Exception as e:
                    entry["status"] = "error"
                    entry["error"] = str(e)
            else:
                # No active session — try TCP probe
                entry.update(await self._tcp_probe(url))

            results.append(entry)

        return results

    @staticmethod
    async def _tcp_probe(url: str) -> dict:
        """TCP-level connectivity check for HTTP-based MCP servers."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            t0 = time.monotonic()
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=3.0
            )
            latency = (time.monotonic() - t0) * 1000
            writer.close()
            await writer.wait_closed()
            return {"status": "reachable", "latency_ms": round(latency, 1)}
        except (asyncio.TimeoutError, OSError) as e:
            return {"status": "offline", "error": str(e)}

    async def shutdown(self) -> None:
        """Close all MCP server connections."""
        if not self._initialized:
            return
        logger.info("Shutting down MCP connections...")
        await self._exit_stack.aclose()
        self._sessions.clear()
        self._tools.clear()
        self._initialized = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        """Load and return the MCP configuration file."""
        if not self.config_path.exists():
            logger.warning("MCP config not found: %s", self.config_path)
            return {"servers": []}
        with open(self.config_path, encoding="utf-8") as f:
            return json.load(f)

    async def _connect_server(self, config: dict) -> None:
        """Connect to a single MCP server and register its tools."""
        name = config["name"]
        transport = config.get("transport", "stdio")

        # Docker 환경이면 url_docker 우선 사용
        if os.environ.get("DOCKER_ENV") and "url_docker" in config:
            config = {**config, "url": config["url_docker"]}

        if transport == "stdio":
            session = await self._connect_stdio(config)
        elif transport == "sse":
            session = await self._connect_sse(config)
        elif transport == "streamable_http":
            session = await self._connect_streamable_http(config)
        else:
            logger.warning(
                "Unknown transport '%s' for server '%s'", transport, name
            )
            return

        await session.initialize()
        self._sessions[name] = session

        # Discover tools exposed by the server
        tools_result = await session.list_tools()
        for tool_def in tools_result.tools:
            lc_tool = self._wrap_mcp_tool(name, session, tool_def)
            self._tools.append(lc_tool)
            logger.info("  Loaded tool: %s/%s", name, tool_def.name)

    async def _connect_stdio(self, config: dict) -> ClientSession:
        """Establish a stdio transport connection."""
        server_params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env=config.get("env"),
        )
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        return session

    async def _connect_sse(self, config: dict) -> ClientSession:
        """Establish an SSE transport connection (legacy)."""
        url = config["url"]
        sse_transport = await self._exit_stack.enter_async_context(
            sse_client(url)
        )
        read_stream, write_stream = sse_transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        return session

    async def _connect_streamable_http(self, config: dict) -> ClientSession:
        """Establish a Streamable HTTP transport connection (recommended)."""
        url = config["url"]
        http_transport = await self._exit_stack.enter_async_context(
            streamablehttp_client(url)
        )
        read_stream, write_stream, _ = http_transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        return session

    @staticmethod
    def _build_args_schema(tool_def: Any) -> type | None:
        """Build a Pydantic model from an MCP tool's inputSchema.

        This is critical: without an explicit args_schema, LangChain
        cannot tell the LLM what parameters the tool expects, causing
        validation errors or hallucinated parameter names.
        """
        input_schema = getattr(tool_def, "inputSchema", None)
        if not input_schema or not isinstance(input_schema, dict):
            return None

        properties = input_schema.get("properties", {})
        if not properties:
            return None

        required = set(input_schema.get("required", []))

        _TYPE_MAP = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
        }

        fields: dict[str, Any] = {}
        for fname, prop in properties.items():
            field_type = _TYPE_MAP.get(prop.get("type", "string"), str)
            desc = prop.get("description", "")
            default = prop.get("default", ...)

            if fname in required and default is ...:
                # Required field with no default
                fields[fname] = (field_type, Field(description=desc))
            else:
                # Optional field
                if default is ...:
                    default = None
                    field_type = field_type | None  # type: ignore[assignment]
                fields[fname] = (field_type, Field(default=default, description=desc))

        model_name = f"{tool_def.name}_Args"
        return create_model(model_name, **fields)

    @staticmethod
    def _wrap_mcp_tool(
        server_name: str, session: ClientSession, tool_def: Any
    ) -> StructuredTool:
        """Wrap an MCP tool definition as a LangChain StructuredTool."""

        tool_name = tool_def.name
        # Prefix with server name to avoid collisions across servers
        qualified_name = f"mcp__{server_name}__{tool_name}"

        description = (
            tool_def.description
            or f"Tool '{tool_name}' from MCP server '{server_name}'"
        )

        # Build Pydantic schema so the LLM knows exact parameter names/types
        args_schema = MCPToolManager._build_args_schema(tool_def)
        if args_schema:
            logger.info(
                "  Schema for %s/%s: %s",
                server_name,
                tool_name,
                {k: v.annotation for k, v in args_schema.model_fields.items()},
            )

        async def _call_tool(**kwargs: Any) -> str:
            logger.info(
                "MCP call: %s/%s  args=%s",
                server_name, tool_name, kwargs,
            )
            try:
                result = await session.call_tool(tool_name, arguments=kwargs)
                # Check for MCP-level errors
                if getattr(result, "isError", False):
                    error_text = str(result.content) if hasattr(result, "content") else str(result)
                    logger.error(
                        "MCP error: %s/%s  error=%s",
                        server_name, tool_name, error_text[:500],
                    )
                    return f"Error calling {tool_name}: {error_text}"
                # Extract text content from MCP result
                if hasattr(result, "content") and result.content:
                    texts = []
                    for block in result.content:
                        if hasattr(block, "text"):
                            texts.append(block.text)
                    response = "\n".join(texts) if texts else str(result)
                    logger.info(
                        "MCP result: %s/%s  length=%d  preview=%s",
                        server_name, tool_name, len(response), response[:200],
                    )
                    return response
                return str(result)
            except Exception as e:
                logger.error(
                    "MCP exception: %s/%s  %s: %s",
                    server_name, tool_name, type(e).__name__, e,
                )
                return f"Error calling {tool_name}: {e}"

        return StructuredTool.from_function(
            coroutine=_call_tool,
            name=qualified_name,
            description=description,
            args_schema=args_schema,
        )


# ------------------------------------------------------------------
# Singleton instance used by the rest of the application
# ------------------------------------------------------------------
mcp_manager = MCPToolManager()
