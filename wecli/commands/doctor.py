"""Check Python, AT-SPI, xdotool, and WeChat readiness without sending."""

import os
import sqlite3
import sys

import click

from ..core.context import AppContext
from ..core.desktop import AtspiDesktop, DesktopError
from ..core.runtime import in_conda
from ..core.stream import account_id, message_page
from ..output.formatter import output, readable


@click.command("doctor")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="text")
@click.pass_context
def doctor(ctx, fmt):
    """Check Python, AT-SPI, xdotool, and WeChat readiness without sending."""
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
            "error",
            "Desktop dependencies are not all from the active Conda environment. Update it using environment.yml.",
        )
    result["send_available"] = result["ready"]
    result["read_available"] = False
    try:
        app = AppContext(ctx.obj)
        page = message_page(app, limit=1)
        result.update(read_available=True, account_id=account_id(app), self_id=page["self_id"])
        roots = [
            root
            for process in result.get("wechat_apps", [])
            for root in process.get("database_roots", [])
        ]
        result["account_matches"] = bool(roots) and all(
            os.path.realpath(root) == os.path.realpath(app.db_dir) for root in roots
        )
        result["send_available"] = result["send_available"] and result["account_matches"]
        if not result["account_matches"]:
            result["account_error"] = (
                "Running account differs from configuration or cannot be identified"
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        result["read_error"] = str(exc)
        result["send_available"] = False
    result["ready"] = result["send_available"]
    result["status"] = "ready" if result["ready"] else "not_ready"
    if fmt == "json":
        output(result, "json")
    else:
        details = {key: value for key, value in result.items() if key != "error"}
        output(readable(details))
        if result.get("error"):
            click.echo(f"Error: {result['error']}", err=True)
    if not result["ready"]:
        ctx.exit(1)
