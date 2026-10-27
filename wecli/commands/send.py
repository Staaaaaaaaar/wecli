"""Select a chat and send plain text through AT-SPI (single-display Linux X11)."""

import json
import os
import sqlite3
import sys
import uuid

import click

from ..core.context import AppContext
from ..core.desktop import AtspiDesktop, DesktopError
from ..core.operations import operation_path, save_operation, send_lock
from ..core.sending import LocalReceipt, resolve_recipient, send_contacts
from ..output.formatter import output


@click.command("send")
@click.argument("recipient")
@click.argument("message", required=False)
@click.option(
    "--file",
    "message_file",
    type=click.File("r", encoding="utf-8"),
    help="Read UTF-8 text from a file (- for stdin)",
)
@click.option(
    "--dry-run", is_flag=True, help="Preview recipient and message without operating the desktop"
)
@click.option(
    "--operation-id",
    type=click.UUID,
    help="Caller-generated UUID; retries return the saved attempt",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation for this send")
@click.option("--window-id", type=click.IntRange(min=1), help="WeChat X11 main window ID (decimal)")
@click.option(
    "--timeout",
    type=click.IntRange(min=1, max=30),
    default=8,
    show_default=True,
    help="Timeout in seconds for each UI or local-record stage",
)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="text")
@click.pass_context
def send(
    ctx, recipient, message, message_file, dry_run, operation_id, yes, window_id, timeout, fmt
):
    """Select a chat and send plain text through AT-SPI (single-display Linux X11)."""
    if (message is None) == (message_file is None):
        raise click.UsageError("Provide exactly one of MESSAGE or --file.")
    if message_file is not None:
        try:
            message = message_file.read()
        except (OSError, UnicodeError) as exc:
            raise click.ClickException("Cannot read the UTF-8 message file.") from exc
    message = message.replace("\r\n", "\n")
    if not message.strip() or any(ord(c) < 32 and c not in "\n\t" for c in message):
        raise click.UsageError(
            "Message must not be empty or contain unsupported control characters."
        )
    if not dry_run and not yes and not sys.stdin.isatty():
        raise click.UsageError(
            "Sending without a terminal requires --yes. Use --dry-run to preview."
        )
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
            click.echo(f"Recipient: {name} ({contact['username']})\nMessage:\n{message}", err=True)
            click.confirm(
                "Allow wecli to operate the WeChat window and send this message?",
                default=False,
                abort=True,
                err=True,
            )
        with send_lock():
            attempt_id = str(operation_id or uuid.uuid4())
            path = operation_path(app, attempt_id)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    saved = json.load(handle)
                if saved["recipient"] != result["recipient"] or saved["message"] != message:
                    raise click.ClickException("Operation ID already used for a different send")
                result = saved
            else:
                result["operation_id"] = attempt_id
                _perform_send(app, contact, message, result, window_id, timeout)
    if fmt == "json":
        output(result, "json")
    else:
        output(result, "text")
    if result["status"] in ("unknown", "failed"):
        ctx.exit(3 if result["status"] == "unknown" else 1)


def _perform_send(app, contact, message, result, window_id, timeout):
    result["status"] = "failed"
    try:
        receipt = LocalReceipt(app, contact["username"], message)
    except (OSError, ValueError, sqlite3.Error) as exc:
        result.update(error=str(exc))
        save_operation(app, result)
        return
    result.update(
        status="unknown",
        baseline=[list(k) for k in receipt.baseline],
        cutoff=receipt.cutoff,
        self_username=receipt.self_username,
    )
    save_operation(app, result)
    try:
        response = AtspiDesktop(window_id=window_id, timeout=timeout).send_text(
            contact["ui_names"], message, app.db_dir
        )
    except DesktopError as exc:
        result.update(status="failed", error=str(exc))
        save_operation(app, result)
        return
    result.update(response)
    try:
        record = receipt.wait(timeout)
    except (OSError, ValueError, sqlite3.Error):
        record = None
    if record:
        result.update(status="recorded", local_record_confirmed=True, local_record=record)
        # A local record resolves a lost UI response; it is not delivery proof.
        if result.get("error"):
            result["ui_warning"] = result.pop("error")
    else:
        result.update(
            status="unknown",
            warning="No new outgoing local record confirmed; reconcile before resending.",
        )
    save_operation(app, result)
