# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Detect changed conversation summaries since the previous check.

This is a snapshot comparison, not a complete message stream. Multiple
messages in one chat may be represented by only the latest summary.
The first call returns unread conversation summaries and saves a snapshot."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime

import click

from ..core.config import STATE_DIR, atomic_write_json
from ..core.contacts import get_contact_names
from ..core.messages import decompress_content, format_msg_type
from ..output.formatter import output

STATE_FILE = os.path.join(STATE_DIR, "last_check.json")


def _load_last_state(state_file=None):
    state_file = state_file or STATE_FILE
    if not os.path.exists(state_file):
        return {}
    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict) or any(
            not isinstance(k, str) or type(v) is not int for k, v in state.items()
        ):
            raise ValueError("Snapshot must map chat IDs to integer timestamps")
        return state
    except (ValueError, OSError) as exc:
        raise click.ClickException(
            f"Cannot read snapshot {state_file}: {exc}. Remove it to reset."
        ) from exc


def _save_last_state(state, state_file=None):
    state_file = state_file or STATE_FILE
    atomic_write_json(state_file, state)


@click.command("new-messages")
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.pass_context
def new_messages(ctx, fmt):
    """Detect changed conversation summaries since the previous check.

    This is a snapshot comparison, not a complete message stream. Multiple
    messages in one chat may be represented by only the latest summary.
    The first call returns unread conversation summaries and saves a snapshot."""
    app = ctx.obj

    path = app.cache.get(os.path.join("session", "session.db"))
    if not path:
        raise click.ClickException("Cannot decrypt session.db")

    names = get_contact_names(app.cache, app.decrypted_dir)
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("""
            SELECT username, unread_count, summary, last_timestamp,
                   last_msg_type, last_msg_sender, last_sender_display_name
            FROM SessionTable
            WHERE last_timestamp > 0
            ORDER BY last_timestamp DESC
        """).fetchall()

    curr_state = {}
    for r in rows:
        username, unread, summary, ts, msg_type, sender, sender_name = r
        curr_state[username] = {
            "unread": unread,
            "summary": summary,
            "timestamp": ts,
            "msg_type": msg_type,
            "sender": sender or "",
            "sender_name": sender_name or "",
        }

    import hashlib

    account = hashlib.sha256(os.path.realpath(app.db_dir).encode()).hexdigest()[:16]
    state_file = os.path.join(os.path.dirname(app.keys_file), f"last_check_{account}.json")
    last_state = _load_last_state(state_file)

    if not last_state:
        # 首次调用：保存状态，返回未读

        unread_msgs = []
        for username, s in curr_state.items():
            if s["unread"] and s["unread"] > 0:
                display = names.get(username, username)
                is_group = "@chatroom" in username
                summary = s["summary"]
                if isinstance(summary, bytes):
                    summary = decompress_content(summary, 4) or "(compressed content)"
                if isinstance(summary, str) and ":\n" in summary:
                    summary = summary.split(":\n", 1)[1]
                time_str = datetime.fromtimestamp(s["timestamp"]).strftime("%H:%M")
                unread_msgs.append(
                    {
                        "chat": display,
                        "username": username,
                        "is_group": is_group,
                        "unread": s["unread"],
                        "last_message": str(summary or ""),
                        "msg_type": format_msg_type(s["msg_type"]),
                        "time": time_str,
                        "timestamp": s["timestamp"],
                    }
                )

        if fmt == "json":
            output(
                {"first_call": True, "unread_count": len(unread_msgs), "messages": unread_msgs},
                "json",
            )
        else:
            if unread_msgs:
                lines = []
                for m in unread_msgs:
                    tag = " [Group]" if m["is_group"] else ""
                    lines.append(
                        f"[{m['time']}] {m['chat']}{tag} ({m['unread']} unread): {m['last_message']}"
                    )
                output(f"Unread conversations ({len(unread_msgs)}):\n\n" + "\n".join(lines), "text")
            else:
                output("No unread conversations. Snapshot saved for the next check.", "text")
        _save_last_state({u: s["timestamp"] for u, s in curr_state.items()}, state_file)
        return

    # 后续调用：对比差异
    new_msgs = []
    for username, s in curr_state.items():
        prev_ts = last_state.get(username, 0)
        if s["timestamp"] > prev_ts:
            display = names.get(username, username)
            is_group = "@chatroom" in username
            summary = s["summary"]
            if isinstance(summary, bytes):
                summary = decompress_content(summary, 4) or "(compressed content)"
            if isinstance(summary, str) and ":\n" in summary:
                summary = summary.split(":\n", 1)[1]

            sender_display = ""
            if is_group and s["sender"]:
                sender_display = names.get(s["sender"], s["sender_name"] or s["sender"])

            new_msgs.append(
                {
                    "chat": display,
                    "username": username,
                    "is_group": is_group,
                    "last_message": str(summary or ""),
                    "msg_type": format_msg_type(s["msg_type"]),
                    "sender": sender_display,
                    "time": datetime.fromtimestamp(s["timestamp"]).strftime("%H:%M:%S"),
                    "timestamp": s["timestamp"],
                }
            )

    new_msgs.sort(key=lambda m: m["timestamp"])

    if fmt == "json":
        output({"first_call": False, "new_count": len(new_msgs), "messages": new_msgs}, "json")
    else:
        if not new_msgs:
            output("No changed conversation summaries.", "text")
        else:
            lines = []
            for m in new_msgs:
                entry = f"[{m['time']}] {m['chat']}"
                if m["is_group"]:
                    entry += " [Group]"
                entry += f": {m['msg_type']}"
                if m["sender"]:
                    entry += f" ({m['sender']})"
                entry += f" - {m['last_message']}"
                lines.append(entry)
            output(
                f"Changed conversation summaries ({len(new_msgs)}):\n\n" + "\n".join(lines), "text"
            )

    _save_last_state({u: s["timestamp"] for u, s in curr_state.items()}, state_file)
