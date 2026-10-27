"""Send plain text using AT-SPI identification and direct EditableText input."""

import sqlite3

import click

from ..core.context import AppContext
from ..core.desktop import AtspiDesktop, DesktopError
from ..core.sending import LocalReceipt, resolve_recipient, send_contacts
from ..output.formatter import output


@click.command("send")
@click.argument("recipient")
@click.argument("message", required=False)
@click.option(
    "--file",
    "message_file",
    type=click.File("r", encoding="utf-8"),
    help="从 UTF-8 文件读取文本（- 表示 stdin）",
)
@click.option("--dry-run", is_flag=True, help="只解析收件人及文本，不操作桌面")
@click.option("--yes", "-y", is_flag=True, help="跳过一次发送确认，供脚本调用")
@click.option(
    "--window-id", type=click.IntRange(min=1), help="指定微信 X11 主窗口十进制 ID"
)
@click.option(
    "--timeout",
    type=click.IntRange(min=1, max=30),
    default=8,
    show_default=True,
    help="每阶段界面或本地记录等待秒数",
)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def send(ctx, recipient, message, message_file, dry_run, yes, window_id, timeout, fmt):
    """通过 AT-SPI 自动选择聊天并发送文本（单屏 Linux X11）。

    \b
    wecli send filehelper "你好" --dry-run
    wecli send filehelper "你好" --yes
    wecli send "唯一备注" --file message.txt
    """
    if (message is None) == (message_file is None):
        raise click.UsageError("必须且只能提供 MESSAGE 或 --file。")
    if message_file is not None:
        try:
            message = message_file.read()
        except (OSError, UnicodeError) as exc:
            raise click.ClickException("无法读取 UTF-8 消息文件。") from exc
    message = message.replace("\r\n", "\n")
    if not message.strip() or any(ord(c) < 32 and c not in "\n\t" for c in message):
        raise click.UsageError("消息不能为空或包含不支持的控制字符。")
    try:
        app = AppContext(ctx.obj)
        contact = resolve_recipient(recipient, send_contacts(app))
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise click.ClickException(str(exc)) from exc
    name = contact["remark"] or contact["nick_name"] or contact["username"]
    result = dict(
        status="dry_run",
        recipient=contact["username"],
        display_name=name,
        message=message,
        backend="atspi",
        ui_confirmed=False,
        local_record_confirmed=False,
    )
    if not dry_run:
        if not yes:
            click.echo(
                f"收件人: {name} ({contact['username']})\n消息:\n{message}", err=True
            )
            click.confirm(
                "允许 wecli 操作微信窗口并发送？", default=False, abort=True, err=True
            )
        try:
            receipt = LocalReceipt(app, contact["username"], message)
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise click.ClickException(
                "无法读取发送前本地记录，尚未操作桌面。"
            ) from exc
        try:
            response = AtspiDesktop(window_id=window_id, timeout=timeout).send_text(
                contact["ui_names"], message, app.db_dir
            )
        except DesktopError as exc:
            raise click.ClickException(str(exc)) from exc
        result.update(response)
        try:
            record = receipt.wait(timeout)
        except (OSError, ValueError, sqlite3.Error):
            record = None
        if record:
            result.update(
                status="recorded", local_record_confirmed=True, local_record=record
            )
            # A local record resolves a lost UI response; it is not delivery proof.
            if result.get("error"):
                result["ui_warning"] = result.pop("error")
        elif not result.get("ui_confirmed"):
            result.update(status="unknown")
        else:
            result["warning"] = (
                "界面已更新，但未确认新增本人本地记录；请先核对，勿直接重发。"
            )
    if fmt == "json":
        output(result)
    else:
        output(
            f"{result['status']}: {name} ({contact['username']})\n{message}"
            + (
                f"\n{result.get('error') or result.get('warning')}"
                if result.get("error") or result.get("warning")
                else ""
            ),
            "text",
        )
    if result["status"] == "unknown":
        ctx.exit(3)
