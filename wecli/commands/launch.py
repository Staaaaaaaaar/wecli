"""Launch the official app with accessibility and without Conda library injection."""

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
        if (
            len(apps) == 1
            and apps[0].get("pid") in pids
            and apps[0].get("database_roots") == []
        ):
            return dict(
                status="awaiting_login",
                pids=pids,
                atspi_ready=False,
                message="微信已启动，请用户自行完成登录，然后运行 wecli doctor。",
            )
        if report.get("status") != "ready":
            raise DesktopError(
                "微信已运行，但未通过桌面检查。请运行 wecli doctor；如需重新启用辅助功能，先处理未完成操作，再运行 wecli launch --restart。"
            )
        return dict(status="already_running", pids=pids, atspi_ready=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise DesktopError(f"微信程序不存在或不可执行: {executable}")
    if not os.environ.get("DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        raise DesktopError("请在本机 X11 图形会话中运行。")
    if pids:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        while wechat_processes():
            if time.monotonic() >= deadline:
                raise DesktopError("微信未在 10 秒内退出，已停止；不会强制终止进程。")
            time.sleep(0.2)
    log_path = Path.home() / ".wecli" / "wechat.log"
    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(
        log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600
    )
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
        raise DesktopError(f"微信启动后退出，请检查 {log_path}")
    return dict(
        status="started",
        pid=process.pid,
        executable=str(executable),
        log=str(log_path),
        message="请用户在微信窗口自行完成登录，然后运行 wecli doctor。",
    )


@click.command("launch")
@click.option(
    "--executable",
    type=click.Path(path_type=Path),
    default="/usr/bin/wechat",
    show_default=True,
)
@click.option(
    "--restart", is_flag=True, help="关闭已有微信再启动；请先处理未完成的文件传输和编辑"
)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
def launch(executable, restart, fmt):
    """带辅助功能参数启动官方微信；默认复用已有微信，登录由用户自行完成。"""
    try:
        result = start_wechat(executable.expanduser().absolute(), restart)
    except (OSError, DesktopError) as exc:
        raise click.ClickException(str(exc)) from exc
    output(
        result
        if fmt == "json"
        else result["status"] + "\n" + result.get("message", ""),
        fmt,
    )
