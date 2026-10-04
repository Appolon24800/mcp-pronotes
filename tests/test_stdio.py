"""Exercise the real MCP stdio transport without authenticating to PRONOTE."""

import json
import os
from pathlib import Path
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_list_and_validate_tools(self):
        root = Path(__file__).resolve().parents[1]
        env = {key: value for key, value in os.environ.items() if not key.startswith("PRONOTE_")}
        params = StdioServerParameters(
            command=sys.executable, args=[str(root / "server.py")], cwd=str(root), env=env,
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                self.assertEqual(initialized.serverInfo.name, "pronotes")
                listed = await session.list_tools()
                self.assertEqual(len(listed.tools), 31)
                blocked = await session.call_tool("create_discussion", {
                    "subject": "Fictional", "message": "Fictional", "recipient_ids": ["fictional"], "confirm": True,
                })
                self.assertIn("disabled", json.loads(blocked.content[0].text)["error"])
                # The server validates inputs and returns structured refusals.
                rejected = await session.call_tool("get_timetable", {"unexpected": True})
                self.assertFalse(rejected.isError)
                self.assertEqual(rejected.structuredContent["error_code"], "INVALID_ARGUMENT")
                unconfirmed = await session.call_tool("create_discussion", {
                    "subject": "Fictional", "message": "Fictional", "recipient_ids": ["fictional"],
                })
                self.assertFalse(unconfirmed.isError)
                self.assertEqual(unconfirmed.structuredContent["error_code"], "CONFIRMATION_REQUIRED")
                unknown = await session.call_tool("unknown_tool", {})
                self.assertIn("Unknown tool", json.loads(unknown.content[0].text)["error"])


if __name__ == "__main__":
    unittest.main()
