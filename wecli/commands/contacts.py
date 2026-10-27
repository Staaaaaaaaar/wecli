# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""List contacts or show details for an exact contact."""

import click

from ..core.contacts import get_contact_detail, get_contact_full, resolve_username
from ..output.formatter import output, table


@click.command("contacts")
@click.option("--query", default="", help="Match nickname, remark, or wxid")
@click.option("--detail", default=None, help="Show details for a nickname, remark, or wxid")
@click.option(
    "--limit",
    default=50,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum number of results",
)
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.pass_context
def contacts(ctx, query, detail, limit, fmt):
    """List contacts or show details for an exact contact."""
    app = ctx.obj

    if detail:
        _show_detail(app, detail, fmt)
        return

    full = get_contact_full(app.cache, app.decrypted_dir)

    if query:
        q_lower = query.lower()
        matched = [
            c
            for c in full
            if q_lower in c.get("nick_name", "").lower()
            or q_lower in c.get("remark", "").lower()
            or q_lower in c.get("username", "").lower()
        ]
    else:
        matched = full

    matched = matched[:limit]

    if fmt == "json":
        output(matched, "json")
    else:
        if not matched:
            output("No contacts found.")
            return
        output(
            table(
                ["NAME", "USERNAME", "REMARK"],
                [
                    (c["remark"] or c["nick_name"] or c["username"], c["username"], c["remark"])
                    for c in matched
                ],
                [28, 40, 32],
            )
        )


def _show_detail(app, name_or_id, fmt):
    """显示联系人详情。"""

    # 尝试解析为 username
    username = resolve_username(name_or_id, app.cache, app.decrypted_dir)
    if not username:
        # 直接用原始输入试试
        username = name_or_id

    info = get_contact_detail(username, app.cache, app.decrypted_dir)
    if not info:
        raise click.ClickException(f"Contact not found: {name_or_id}")

    if fmt == "json":
        output(info, "json")
    else:
        lines = [f"Contact details: {info['nick_name']}"]
        if info["remark"]:
            lines.append(f"Remark: {info['remark']}")
        if info["alias"]:
            lines.append(f"WeChat ID: {info['alias']}")
        lines.append(f"wxid: {info['username']}")
        if info["description"]:
            lines.append(f"Bio: {info['description']}")
        if info["is_group"]:
            lines.append("Type: Group")
        elif info["is_subscription"]:
            lines.append("Type: Subscription")
        elif info["verify_flag"] and info["verify_flag"] >= 8:
            lines.append("Type: Verified organization")
        if info["avatar"]:
            lines.append(f"Avatar: {info['avatar']}")
        output("\n".join(lines), "text")
