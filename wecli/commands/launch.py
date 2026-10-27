"""Start WeChat with accessibility enabled; sign in using the app window."""

import os
import signal
import subprocess
import time
from pathlib import Path

import click

from ..core.desktop import AtspiDesktop, DesktopError
from ..core.runtime import clean_wechat_env, wechat_processes
from ..output.formatter import output


def start_wechat(executable, restart=False):
    pids = wechat_processes()
    if pids and not restart:
        report = AtspiDesktop(timeout=2).inspect()
        apps = report.get("wechat_apps", [])
        if len(apps) == 1 and apps[0].get("pid") in pids and apps[0].get("database_roots") == []:
            return dict(
                status="awaiting_login",
                pids=pids,
                atspi_ready=False,
                message="WeChat is running. Sign in, then run wecli doctor.",
            )
        if report.get("status") != "ready":
            raise DesktopError(
                "WeChat is running but desktop checks failed. Run wecli doctor. To enable accessibility again, finish pending work and run wecli launch --restart."
            )
        return dict(status="already_running", pids=pids, atspi_ready=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise DesktopError(f"WeChat executable is missing or not executable: {executable}")
    if not os.environ.get("DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        raise DesktopError("Run this command in a local X11 desktop session.")
    if pids:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        while wechat_processes():
            if time.monotonic() >= deadline:
                raise DesktopError(
                    "WeChat did not exit within 10 seconds. Stopped without forcibly killing it."
                )
            time.sleep(0.2)
    log_path = Path.home() / ".wecli" / "wechat.log"
    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "ab") as log:
        process = subprocess.Popen(
            [str(executable)],
            env=clean_wechat_env(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    time.sleep(0.5)
    if process.poll() is not None:
        raise DesktopError(f"WeChat exited after launch. Check {log_path}")
    return dict(
        status="started",
        pid=process.pid,
        executable=str(executable),
        log=str(log_path),
        message="Sign in using the WeChat window, then run wecli doctor.",
    )


@click.command("launch")
@click.option(
    "--executable",
    type=click.Path(path_type=Path),
    default="/usr/bin/wechat",
    show_default=True,
)
@click.option(
    "--restart", is_flag=True, help="Restart WeChat; finish pending transfers and edits first"
)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="text")
def launch(executable, restart, fmt):
    """Start WeChat with accessibility enabled; sign in using the app window."""
    try:
        result = start_wechat(executable.expanduser().absolute(), restart)
    except (OSError, DesktopError) as exc:
        raise click.ClickException(str(exc)) from exc
    output(
        result,
        fmt,
    )
