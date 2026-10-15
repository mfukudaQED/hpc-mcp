"""Execute locally configured, fixed-argument, unprivileged site commands."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile

from .config import Settings, SiteTool
from .security import limited


def run_site_tool(settings: Settings, tool: SiteTool) -> dict:
    """Run a configured command with no shell and bounded output and runtime."""
    if not settings.enable_site_tools or tool not in settings.site_tools:
        raise PermissionError("Site tools are disabled")
    with tempfile.TemporaryFile(mode="w+b") as output:
        process = subprocess.Popen(
            list(tool.argv), cwd=tool.cwd, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, close_fds=True,
            start_new_session=True,
        )
        try:
            exit_code = process.wait(timeout=tool.timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            return {"tool": tool.name, "timeout": True, "message": "Site command exceeded timeout"}
        output.seek(0)
        data = output.read(settings.max_output_chars * 4 + 1)
        output.seek(0, os.SEEK_END)
        total_bytes = output.tell()
        text = data.decode("utf-8", errors="replace")
        return {
            "tool": tool.name, "exit_code": exit_code,
            "output": limited(text, settings.max_output_chars),
            "output_truncated": total_bytes > len(data) or len(text) > settings.max_output_chars,
        }
