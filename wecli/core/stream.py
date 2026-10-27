"""Account-bound, replayable message pages. Callers commit cursors after processing."""

import base64
import hashlib
import json
import os
import sqlite3
from contextlib import closing

from .contacts import get_self_username
from .messages import (
    _is_safe_msg_table_name,
    _load_name2id_maps,
    _load_search_contexts_from_db,
    _parse_message_content,
    decompress_content,
)


def account_id(app):
    return hashlib.sha256(os.path.realpath(app.db_dir).encode()).hexdigest()


def encode_cursor(value):
    return base64.urlsafe_b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def decode_cursor(token, account):
    try:
        value = json.loads(base64.b64decode(token, altchars=b"-_", validate=True))
        if value["version"] != 1 or value["account_id"] != account:
            raise ValueError("Cursor account or version mismatch")
        positions = value["positions"]
        if not isinstance(positions, dict) or any(
            not isinstance(k, str) or type(v) is not int or v < 0 for k, v in positions.items()
        ):
            raise ValueError("Invalid cursor positions")
        return value
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "Invalid cursor or account changed; do not reuse another account cursor"
        ) from exc


def message_page(app, cursor=None, limit=100, chat_id=None):
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be between 1 and 10000")
    if not app.msg_db_keys:
        raise ValueError("No message databases configured; run init")
    account = account_id(app)
    state = (
        decode_cursor(cursor, account)
        if cursor
        else dict(version=1, account_id=account, positions={})
    )
    positions = dict(state["positions"])
    self_id = get_self_username(app.db_dir, app.cache, app.decrypted_dir)
    if not self_id:
        raise ValueError("Cannot identify the configured account; run doctor before reading")
    messages = []
    more = False
    seen_sources = set()
    for key in sorted(app.msg_db_keys):
        path = app.cache.get(key)
        if not path:
            raise ValueError(f"Cannot read message database: {key}; cursor was not advanced")
        with closing(sqlite3.connect(path)) as conn:
            senders = _load_name2id_maps(conn)
            for ctx in _load_search_contexts_from_db(conn, path, {}):
                table = ctx["table_name"]
                if not _is_safe_msg_table_name(table):
                    continue
                if not ctx["username"]:
                    raise ValueError(f"Cannot resolve conversation ID for {key}/{table}")
                source = key.replace("\\", "/") + "/" + table
                seen_sources.add(source)
                previous = positions.get(source, 0)
                maximum = conn.execute(f"SELECT MAX(local_id) FROM [{table}]").fetchone()[0] or 0
                if maximum < previous:
                    raise ValueError(f"Message source reset: {source}; manual recovery required")
                if chat_id and ctx["username"] != chat_id:
                    continue
                remaining = limit - len(messages)
                rows = conn.execute(
                    f"SELECT local_id, local_type, create_time, real_sender_id, "
                    f"message_content, WCDB_CT_message_content FROM [{table}] "
                    "WHERE local_id > ? ORDER BY local_id LIMIT ?",
                    (previous, remaining + 1),
                ).fetchall()
                more = more or len(rows) > remaining
                for local_id, kind, timestamp, sender, body, compression in rows[:remaining]:
                    content = decompress_content(body, compression)
                    prefix, text = _parse_message_content(content, kind, ctx["is_group"])
                    sender_id = senders.get(sender)
                    if ctx["is_group"] and sender_id == ctx["username"]:
                        sender_id = prefix or None
                    sender_id = sender_id or prefix or None
                    identity = f"{account}/{source}/{local_id}"
                    messages.append(
                        dict(
                            message_id=hashlib.sha256(identity.encode()).hexdigest(),
                            account_id=account,
                            chat_id=ctx["username"],
                            sender_id=sender_id,
                            is_self=(sender_id == self_id) if sender_id else None,
                            timestamp=timestamp,
                            type=kind,
                            text=text,
                            content=content,
                            local_id=local_id,
                            source=source,
                        )
                    )
                    positions[source] = local_id
    missing = set(state["positions"]) - seen_sources
    if missing:
        raise ValueError(
            "Message sources disappeared; cursor was not advanced: " + ", ".join(sorted(missing))
        )
    state["positions"] = positions
    return dict(
        account_id=account,
        self_id=self_id,
        messages=messages,
        count=len(messages),
        has_more=more,
        next_cursor=encode_cursor(state),
    )
