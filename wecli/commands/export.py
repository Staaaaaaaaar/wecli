# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Export chat history as Markdown or plain text."""

from datetime import datetime

import click

from ..core.contacts import get_contact_names
from ..core.messages import (
    collect_chat_history,
    parse_time_range,
    resolve_chat_context,
    validate_pagination,
)
from ..output.formatter import output


@click.command("export")
@click.argument("chat_name")
@click.option(
    "--format",
    "fmt",
    default="markdown",
    type=click.Choice(["markdown", "txt"]),
    help="Export format",
)
@click.option("--output", "output_path", default=None, help="Output file (defaults to stdout)")
@click.option("--start-time", default="", help="Start time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="End time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option(
    "--limit",
    default=500,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of messages to export",
)
@click.pass_context
def export(ctx, chat_name, fmt, output_path, start_time, end_time, limit):
    """Export chat history as Markdown or plain text."""
    app = ctx.obj

    try:
        validate_pagination(limit, 0, limit_max=None)
        start_ts, end_ts = parse_time_range(start_time, end_time)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(2)

    chat_ctx = resolve_chat_context(chat_name, app.msg_db_keys, app.cache, app.decrypted_dir)
    if not chat_ctx:
        raise click.ClickException(f"Chat not found: {chat_name}")
    if not chat_ctx["db_path"]:
        raise click.ClickException(f"No message history found for {chat_ctx['display_name']}")

    names = get_contact_names(app.cache, app.decrypted_dir)
    lines, failures = collect_chat_history(
        chat_ctx,
        names,
        app.display_name_fn,
        start_ts=start_ts,
        end_ts=end_ts,
        limit=limit,
        offset=0,
    )

    if failures:
        click.echo("Warning: Some message queries failed: " + "; ".join(failures), err=True)
        if not lines:
            raise click.ClickException("No messages could be exported because queries failed.")

    if not lines:
        click.echo(f"No messages found for {chat_ctx['display_name']}", err=True)
        ctx.exit(0)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    chat_type = "Group" if chat_ctx["is_group"] else "Direct"
    time_range = f"{start_time or 'earliest'} ~ {end_time or 'latest'}"

    if fmt == "markdown":
        content = _format_markdown(chat_ctx["display_name"], chat_type, time_range, now, lines)
    else:
        content = _format_txt(chat_ctx["display_name"], chat_type, time_range, now, lines)

    if output_path and output_path != "-":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
        click.echo(f"Exported {len(lines)} messages to: {output_path}", err=True)
    else:
        output(content, "text")


def _format_markdown(display_name, chat_type, time_range, export_time, lines):
    header = (
        f"# Chat history: {display_name}\n\n"
        f"**Time range:** {time_range}\n\n"
        f"**Exported at:** {export_time}\n\n"
        f"**Messages:** {len(lines)}\n\n"
        f"**Type:** {chat_type}\n\n---\n"
    )
    body = "\n".join(f"- {line}" for line in lines)
    return header + body


def _format_txt(display_name, chat_type, time_range, export_time, lines):
    header = (
        f"Chat history: {display_name}\n"
        f"Type: {chat_type}\n"
        f"Time range: {time_range}\n"
        f"Exported at: {export_time}\n"
        f"Messages: {len(lines)}\n"
        f"{'=' * 60}"
    )
    body = "\n".join(lines)
    return header + "\n" + body
