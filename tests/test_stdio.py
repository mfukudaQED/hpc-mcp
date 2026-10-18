"""End-to-end test of JSON-RPC MCP over a real subprocess stdio transport."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_stdio_discovery_and_ping(tmp_path: Path):
    """Negotiate MCP and call a read-only tool through a spawned process."""
    root = tmp_path / "work"
    root.mkdir()
    config = tmp_path / "policy.toml"
    config.write_text(f'[filesystem]\nroots = ["{root}"]\n')

    async def check() -> None:
        """Connect, initialize, enumerate tools, and issue an RPC call."""
        env = {**os.environ, "HPC_MCP_CONFIG": str(config)}
        params = StdioServerParameters(command=sys.executable, args=["-m", "hpc_mcp.server"], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                response = await client.list_tools()
                names = {tool.name for tool in response.tools}
                assert "ping" in names
                assert "execute_command" not in names
                result = await client.call_tool("ping")
                assert not result.isError
                assert any("0.3.0" in getattr(block, "text", "") for block in result.content)

    asyncio.run(check())
