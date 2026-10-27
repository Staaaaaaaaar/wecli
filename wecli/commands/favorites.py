# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""List or search local WeChat favorites."""

import os
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime

import click

from ..core.contacts import get_contact_names
from ..output.formatter import output

_FAV_TYPE_MAP = {
    1: "Text",
    2: "Image",
    5: "Article",
    19: "Contact card",
    20: "Channels",
}

_FAV_TYPE_FILTERS = {
    "text": 1,
    "image": 2,
    "article": 5,
    "card": 19,
    "video": 20,
}


def _parse_fav_content(content, fav_type):
    """从 XML content 提取摘要信息。"""
    if not content:
        return ""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return ""
    item = root if root.tag == "favitem" else root.find(".//favitem")
    if item is None:
        return ""

    if fav_type == 1:
        return (item.findtext("desc") or "").strip()
    if fav_type == 2:
        return "[Saved image]"
    if fav_type == 5:
        title = (item.findtext(".//pagetitle") or "").strip()
        desc = (item.findtext(".//pagedesc") or "").strip()
        return f"{title} - {desc}" if desc else title
    if fav_type == 19:
        return (item.findtext("desc") or "").strip()
    if fav_type == 20:
        nickname = (item.findtext(".//nickname") or "").strip()
        desc = (item.findtext(".//desc") or "").strip()
        parts = [p for p in [nickname, desc] if p]
        return " ".join(parts) if parts else "[Channels]"
    desc = (item.findtext("desc") or "").strip()
    return desc if desc else "[Favorite]"


@click.command("favorites")
@click.option(
    "--limit",
    default=20,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of results",
)
@click.option(
    "--type",
    "fav_type",
    default=None,
    type=click.Choice(list(_FAV_TYPE_FILTERS.keys())),
    help="Filter by favorite type",
)
@click.option("--query", default=None, help="Search by keyword")
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.pass_context
def favorites(ctx, limit, fav_type, query, fmt):
    """List or search local WeChat favorites."""
    app = ctx.obj

    # 查找 favorite.db
    fav_path = None
    pre_decrypted = os.path.join(app.decrypted_dir, "favorite", "favorite.db")
    if os.path.exists(pre_decrypted):
        fav_path = pre_decrypted
    else:
        fav_path = app.cache.get(os.path.join("favorite", "favorite.db"))
    if not fav_path:
        raise click.ClickException("Cannot access favorite.db")

    names = get_contact_names(app.cache, app.decrypted_dir)

    with closing(sqlite3.connect(fav_path)) as conn:
        where_parts = []
        params = []

        if fav_type:
            where_parts.append("type = ?")
            params.append(_FAV_TYPE_FILTERS[fav_type])

        if query:
            where_parts.append("content LIKE ?")
            params.append(f"%{query}%")

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        rows = conn.execute(
            f"""
            SELECT local_id, type, update_time, content, fromusr, realchatname
            FROM fav_db_item
            {where_sql}
            ORDER BY update_time DESC
            LIMIT ?
        """,
            (*params, limit),
        ).fetchall()

    results = []
    for local_id, typ, ts, content, fromusr, realchat in rows:
        from_display = names.get(fromusr, fromusr) if fromusr else ""
        chat_display = names.get(realchat, realchat) if realchat else ""

        summary = _parse_fav_content(content, typ)

        results.append(
            {
                "id": local_id,
                "type": _FAV_TYPE_MAP.get(typ, f"type={typ}"),
                "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "summary": summary,
                "from": from_display,
                "source_chat": chat_display,
            }
        )

    if fmt == "json":
        output(
            {
                "count": len(results),
                "favorites": results,
            },
            "json",
        )
    else:
        if not results:
            output("No favorites found.", "text")
            return
        lines = []
        for r in results:
            entry = f"[{r['time']}] [{r['type']}] {r['summary']}"
            if r["from"]:
                entry += f"\n  From: {r['from']}"
            if r["source_chat"]:
                entry += f"  Chat: {r['source_chat']}"
            lines.append(entry)
        output(f"Favorites ({len(results)}):\n\n" + "\n\n".join(lines), "text")
