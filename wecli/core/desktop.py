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
            raise DesktopError("Sending requires a Linux X11 desktop session.")
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
                error="Desktop inspection timed out."
                if probing
                else "Desktop operation timed out; outcome unknown. Check chat history before resending.",
            )
        except OSError as exc:
            raise DesktopError(
                f"Cannot start Python from the active environment: {sys.executable}。"
            ) from exc
        try:
            response = json.loads(result.stdout)
            allowed = (
                ("ready", "not_ready", "failed") if probing else ("submitted", "unknown", "failed")
            )
            if not isinstance(response, dict) or response.get("status") not in allowed:
                raise ValueError("invalid response")
        except (ValueError, TypeError):
            # A worker crash could occur after clicking Send. Never infer failure.
            return dict(
                status="not_ready" if probing else "unknown",
                ui_confirmed=False,
                error="AT-SPI inspection exited unexpectedly. Check desktop D-Bus access."
                if probing
                else "AT-SPI exited unexpectedly; outcome unknown. Check desktop dependencies and chat history before resending.",
            )
        if response["status"] == "failed" and not probing:
            raise DesktopError(response.get("error", "AT-SPI operation failed."))
        return response
