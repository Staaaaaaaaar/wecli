# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Show message statistics for a chat."""

import click

from ..core.contacts import get_contact_names
from ..core.messages import (
    collect_chat_stats,
    parse_time_range,
    resolve_chat_context,
)
from ..output.formatter import output


@click.command("stats")
@click.argument("chat_name")
@click.option("--start-time", default="", help="Start time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="End time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="Output format"
)
@click.pass_context
def stats(ctx, chat_name, start_time, end_time, fmt):
    """Show message statistics for a chat."""
    app = ctx.obj

    try:
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
    result = collect_chat_stats(
        chat_ctx,
        names,
        app.display_name_fn,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    if fmt == "json":
        output(
            {
                "chat": chat_ctx["display_name"],
                "username": chat_ctx["username"],
                "is_group": chat_ctx["is_group"],
                **result,
            },
            "json",
        )
    else:
        lines = [f"Chat statistics for {chat_ctx['display_name']}"]
        if chat_ctx["is_group"]:
            lines[0] += " [Group]"
        lines.append(f"Total messages: {result['total']}")
        if start_time or end_time:
            lines.append(f"Time range: {start_time or 'earliest'} ~ {end_time or 'latest'}")

        # 类型分布
        lines.append("\nMessage types:")
        for t, cnt in result["type_breakdown"].items():
            pct = cnt / result["total"] * 100 if result["total"] > 0 else 0
            lines.append(f"  {t}: {cnt} ({pct:.1f}%)")

        # 发送者排名
        if result["top_senders"]:
            lines.append("\nTop 10 senders:")
            for s in result["top_senders"]:
                lines.append(f"  {s['name']}: {s['count']}")

        # 24小时分布
        lines.append("\nActivity by hour:")
        max_count = max(result["hourly"].values()) if result["hourly"] else 0
        bar_max = 30
        for h in range(24):
            count = result["hourly"].get(h, 0)
            bar_len = int(count / max_count * bar_max) if max_count > 0 else 0
            bar = "█" * bar_len
            lines.append(f"  {h:02d}:00 |{bar} {count}")

        output("\n".join(lines), "text")
