"""Isolate native AT-SPI calls in the current Python environment."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .runtime import RuntimeErrorDetail, desktop_tool, worker_environment


class DesktopError(RuntimeError):
    pass


class AtspiDesktop:
    def __init__(self, window_id=None, timeout=10):
        self.window_id = window_id
        self.timeout = timeout

    def send_text(self, names, message, db_dir):
        if (
            sys.platform != "linux"
            or os.environ.get("XDG_SESSION_TYPE") == "wayland"
            or not os.environ.get("DISPLAY")
        ):
            raise DesktopError("发送仅支持 Linux X11 图形会话。")
        try:
            tool = desktop_tool("xdotool")
        except RuntimeErrorDetail as exc:
            raise DesktopError(str(exc)) from exc
        request = dict(
            names=names,
            message=message,
            db_dir=db_dir,
            window_id=self.window_id,
            timeout=self.timeout,
            xdotool=tool,
        )
        return self.invoke(request)

    def inspect(self):
        request = dict(operation="inspect", timeout=self.timeout)
        try:
            request["xdotool"] = desktop_tool("xdotool")
        except RuntimeErrorDetail as exc:
            return dict(
                status="not_ready",
                python=sys.executable,
                prefix=sys.prefix,
                error=str(exc),
            )
        return self.invoke(request)

    def invoke(self, request):
        probing = request.get("operation") == "inspect"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).with_name("atspi_worker.py")),
                ],
                input=json.dumps(request, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=self.timeout * 5 + 15,
                env=worker_environment(),
            )
        except subprocess.TimeoutExpired:
            return dict(
                status="not_ready" if probing else "unknown",
                ui_confirmed=False,
                error="桌面检查超时。"
                if probing
                else "桌面操作超时，结果未知；先检查聊天记录，不要直接重发。",
            )
        except OSError as exc:
            raise DesktopError(
                f"无法启动当前环境的 Python: {sys.executable}。"
            ) from exc
        try:
            response = json.loads(result.stdout)
            allowed = (
                ("ready", "not_ready", "failed")
                if probing
                else ("submitted", "unknown", "failed")
            )
            if not isinstance(response, dict) or response.get("status") not in allowed:
                raise ValueError("invalid response")
        except (ValueError, TypeError):
            # A worker crash could occur after clicking Send. Never infer failure.
            return dict(
                status="not_ready" if probing else "unknown",
                ui_confirmed=False,
                error="AT-SPI 检查进程异常退出；请确认桌面 D-Bus 可访问。"
                if probing
                else "AT-SPI 进程异常退出，结果未知；检查桌面依赖和聊天记录，不要直接重发。",
            )
        if response["status"] == "failed" and not probing:
            raise DesktopError(response.get("error", "AT-SPI 操作失败。"))
        return response
