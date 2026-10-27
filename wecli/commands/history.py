# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Show recent messages in a chat."""

import click

from ..core.contacts import get_contact_names
from ..core.messages import (
    MSG_TYPE_FILTERS,
    MSG_TYPE_NAMES,
    collect_chat_history,
    parse_time_range,
    resolve_chat_context,
    validate_pagination,
)
from ..output.formatter import output


@click.command("history")
@click.argument("chat_name")
@click.option(
    "--limit",
    default=50,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of messages",
)
@click.option(
    "--offset",
    default=0,
    type=click.IntRange(min=0),
    show_default=True,
    help="Number of results to skip",
)
@click.option("--start-time", default="", help="Start time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="End time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.option(
    "--type",
    "msg_type",
    default=None,
    type=click.Choice(MSG_TYPE_NAMES),
    help="Filter by message type",
)
@click.option(
    "--media", is_flag=True, help="Resolve local media paths (images, files, videos, audio)"
)
@click.pass_context
def history(ctx, chat_name, limit, offset, start_time, end_time, fmt, msg_type, media):
    """Show recent messages in a chat."""
    app = ctx.obj

    try:
        validate_pagination(limit, offset, limit_max=None)
        start_ts, end_ts = parse_time_range(start_time, end_time)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(2)

    chat_ctx = resolve_chat_context(chat_name, app.msg_db_keys, app.cache, app.decrypted_dir)
    if not chat_ctx:
        raise click.ClickException(f"Chat not found: {chat_name}")
    if not chat_ctx["db_path"]:
        raise click.ClickException(f"No message history found for {chat_ctx['display_name']}")

    if fmt == "json":
        from ..core.stream import message_page

        records = []
        cursor = None
        while True:
            page = message_page(app, cursor, 10000, chat_id=chat_ctx["username"])
            records.extend(
                m
                for m in page["messages"]
                if (start_ts is None or m["timestamp"] >= start_ts)
                and (end_ts is None or m["timestamp"] <= end_ts)
                and (not msg_type or (m["type"] & 0xFFFFFFFF) == MSG_TYPE_FILTERS[msg_type][0])
                and (
                    not msg_type
                    or len(MSG_TYPE_FILTERS[msg_type]) == 1
                    or (m["type"] >> 32) == MSG_TYPE_FILTERS[msg_type][1]
                )
            )
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
        records.sort(key=lambda m: (m["timestamp"], m["source"], m["local_id"]), reverse=True)
        output(
            dict(
                account_id=page["account_id"],
                chat_id=chat_ctx["username"],
                messages=records[offset : offset + limit],
                failures=None,
            ),
            "json",
        )
        return

    names = get_contact_names(app.cache, app.decrypted_dir)
    type_filter = MSG_TYPE_FILTERS[msg_type] if msg_type else None
    lines, failures = collect_chat_history(
        chat_ctx,
        names,
        app.display_name_fn,
        start_ts=start_ts,
        end_ts=end_ts,
        limit=limit,
        offset=offset,
        msg_type_filter=type_filter,
        resolve_media=media,
        db_dir=app.db_dir,
    )

    if failures and fmt == "text":
        click.echo("Warning: Some message queries failed: " + "; ".join(failures), err=True)

    if fmt == "json":
        output(
            {
                "chat": chat_ctx["display_name"],
                "username": chat_ctx["username"],
                "is_group": chat_ctx["is_group"],
                "count": len(lines),
                "offset": offset,
                "limit": limit,
                "start_time": start_time or None,
                "end_time": end_time or None,
                "type": msg_type or None,
                "messages": lines,
                "failures": failures if failures else None,
            },
            "json",
        )
    else:
        header = f"History for {chat_ctx['display_name']} ({len(lines)} messages, offset={offset}, limit={limit})"
        if chat_ctx["is_group"]:
            header += " [Group]"
        if start_time or end_time:
            header += f"\nTime range: {start_time or 'earliest'} ~ {end_time or 'latest'}"
        if lines:
            output(header + ":\n\n" + "\n".join(lines), "text")
        else:
            output(f"No messages found for {chat_ctx['display_name']}", "text")
