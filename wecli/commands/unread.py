# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""List unread conversations."""

import os
import sqlite3
from contextlib import closing
from datetime import datetime

import click

from ..core.contacts import get_contact_names
from ..core.messages import decompress_content, format_msg_type
from ..output.formatter import output, table


@click.command("unread")
@click.option(
    "--limit",
    default=50,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of conversations",
)
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.pass_context
def unread(ctx, limit, fmt):
    """List unread conversations."""
    app = ctx.obj

    path = app.cache.get(os.path.join("session", "session.db"))
    if not path:
        raise click.ClickException("Cannot decrypt session.db")

    names = get_contact_names(app.cache, app.decrypted_dir)
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(
            """
            SELECT username, unread_count, summary, last_timestamp,
                   last_msg_type, last_msg_sender, last_sender_display_name
            FROM SessionTable
            WHERE unread_count > 0
            ORDER BY last_timestamp DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

    results = []
    for r in rows:
        username, unread, summary, ts, msg_type, sender, sender_name = r
        display = names.get(username, username)
        is_group = "@chatroom" in username

        if isinstance(summary, bytes):
            summary = decompress_content(summary, 4) or "(compressed content)"
        if isinstance(summary, str) and ":\n" in summary:
            summary = summary.split(":\n", 1)[1]

        sender_display = ""
        if is_group and sender:
            sender_display = names.get(sender, sender_name or sender)

        results.append(
            {
                "chat": display,
                "username": username,
                "is_group": is_group,
                "unread": unread or 0,
                "last_message": str(summary or ""),
                "msg_type": format_msg_type(msg_type),
                "sender": sender_display,
                "timestamp": ts,
                "time": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M"),
            }
        )

    if fmt == "json":
        output(results, "json")
    else:
        if not results:
            output("No unread conversations.")
            return
        output(
            table(
                ["TIME", "CHAT", "UNREAD", "LAST MESSAGE"],
                [
                    (
                        r["time"],
                        r["chat"] + (" [Group]" if r["is_group"] else ""),
                        r["unread"],
                        (r["sender"] + ": " if r["sender"] else "") + r["last_message"],
                    )
                    for r in results
                ],
                [11, 28, 6, 60],
            )
        )
