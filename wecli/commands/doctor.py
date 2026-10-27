"""Check Python, AT-SPI, xdotool, and WeChat readiness without sending."""

import sys

import click

from ..core.desktop import AtspiDesktop, DesktopError
from ..core.runtime import in_conda
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
    if fmt == "json":
        output(result, "json")
    else:
        details = {key: value for key, value in result.items() if key != "error"}
        output(readable(details))
        if result.get("error"):
            click.echo(f"Error: {result['error']}", err=True)
    if not result["ready"]:
        ctx.exit(1)
