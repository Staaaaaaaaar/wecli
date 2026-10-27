"""Read-only desktop runtime diagnostics; no database keys required."""

import sys

import click

from ..core.desktop import AtspiDesktop, DesktopError
from ..core.runtime import in_conda
from ..output.formatter import output


@click.command("doctor")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def doctor(ctx, fmt):
    """检查当前 Python、AT-SPI、xdotool 和微信状态，不发送消息。"""
    try:
        result = AtspiDesktop(timeout=3).inspect()
    except DesktopError as exc:
        result = dict(status="not_ready", error=str(exc))
    result.setdefault("python", sys.executable)
    result.setdefault("prefix", sys.prefix)
    result["conda_environment"] = in_conda()
    result["ready"] = result["status"] == "ready"
    if result["conda_environment"] and not result.get("dependencies_in_prefix"):
        result["ready"] = False
        result["status"] = "not_ready"
        result.setdefault(
            "error", "桌面依赖未完整来自当前 Conda 环境，请按 environment.yml 更新。"
        )
    if fmt == "json":
        output(result)
    else:
        lines = [
            f"状态: {result['status']}",
            f"Python: {result['python']}",
            f"环境: {result['prefix']}",
        ]
        for key in ("gi_path", "xdotool", "dependencies_in_prefix"):
            if key in result:
                lines.append(f"{key}: {result[key]}")
        if result.get("error"):
            lines.append(result["error"])
        output("\n".join(lines), "text")
    if not result["ready"]:
        ctx.exit(1)
