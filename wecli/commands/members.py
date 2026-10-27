# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""List members of a group chat."""

import click

from ..core.contacts import get_contact_names, get_group_members, resolve_username
from ..output.formatter import output


@click.command("members")
@click.argument("group_name")
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.pass_context
def members(ctx, group_name, fmt):
    """List members of a group chat."""
    app = ctx.obj

    username = resolve_username(group_name, app.cache, app.decrypted_dir)
    if not username:
        raise click.ClickException(f"Not found: {group_name}")

    if "@chatroom" not in username:
        raise click.ClickException(f"{group_name} is not a group chat")

    names = get_contact_names(app.cache, app.decrypted_dir)
    display_name = names.get(username, username)

    result = get_group_members(username, app.cache, app.decrypted_dir)

    if fmt == "json":
        output(
            {
                "group": display_name,
                "username": username,
                "member_count": len(result["members"]),
                "owner": result["owner"],
                "members": result["members"],
            },
            "json",
        )
    else:
        lines = []
        for member in result["members"]:
            line = f"{member['display_name']}  ({member['username']})"
            if member["remark"]:
                line += f"  Remark: {member['remark']}"
            lines.append(line)
        if not lines:
            lines.append("No members found.")
        header = f"Members of {display_name} ({len(result['members'])})"
        if result["owner"]:
            header += f", owner: {result['owner']}"
        output(header + ":\n\n" + "\n".join(lines), "text")
