import json
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


class McpGatewayClient:
    def __init__(self, gateway_url: str) -> None:
        self.gateway_url = gateway_url.rstrip("/")

    def server_url(self, server: str) -> str:
        return f"{self.gateway_url}/servers/{server}/sse"

    @asynccontextmanager
    async def session(self, server: str):
        async with sse_client(self.server_url(server)) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                yield session

    async def list_tools(self, server: str) -> list[str]:
        async with self.session(server) as session:
            tools = await session.list_tools()
            return [tool.name for tool in tools.tools]

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        async with self.session(server) as session:
            result = await session.call_tool(tool_name, arguments or {})
            return self._decode_tool_result(result)

    async def call_first_available(
        self,
        server: str,
        candidate_tools: list[str],
        arguments: dict[str, Any] | None = None,
    ) -> tuple[str, Any]:
        available = await self.list_tools(server)
        for candidate in candidate_tools:
            if candidate in available:
                return candidate, await self.call_tool(server, candidate, arguments)
        raise RuntimeError(f"No matching tool on {server}. Tried {candidate_tools}; available={available}")

    def _decode_tool_result(self, result: Any) -> Any:
        if getattr(result, "isError", False):
            return {"error": self._content_to_text(result.content)}
        text = self._content_to_text(result.content)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def _content_to_text(self, content: Any) -> str:
        pieces: list[str] = []
        for item in content or []:
            text = getattr(item, "text", None)
            if text is not None:
                pieces.append(text)
        return "\n".join(pieces)
