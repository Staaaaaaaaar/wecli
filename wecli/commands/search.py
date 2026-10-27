# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Search message content across one or more chats."""

import click

from ..core.contacts import get_contact_names
from ..core.messages import (
    MSG_TYPE_FILTERS,
    MSG_TYPE_NAMES,
    _candidate_page_size,
    _page_ranked_entries,
    collect_chat_search,
    parse_time_range,
    resolve_chat_context,
    resolve_chat_contexts,
    search_all_messages,
    validate_pagination,
)
from ..output.formatter import output


@click.command("search")
@click.argument("keyword")
@click.option("--chat", multiple=True, help="Restrict to a chat (repeatable)")
@click.option("--start-time", default="", help="Start time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="End time: YYYY-MM-DD [HH:MM[:SS]]")
@click.option(
    "--limit",
    default=20,
    type=click.IntRange(1, 500),
    show_default=True,
    help="Maximum number of results (up to 500)",
)
@click.option(
    "--offset",
    default=0,
    type=click.IntRange(min=0),
    show_default=True,
    help="Number of results to skip",
)
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
@click.pass_context
def search(ctx, keyword, chat, start_time, end_time, limit, offset, fmt, msg_type):
    """Search message content across one or more chats."""
    if not keyword.strip():
        raise click.BadParameter("Keyword must not be empty", param_hint="keyword")
    app = ctx.obj

    try:
        validate_pagination(limit, offset)
        start_ts, end_ts = parse_time_range(start_time, end_time)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(2)

    names = get_contact_names(app.cache, app.decrypted_dir)
    candidate_limit = _candidate_page_size(limit, offset)
    chat_names = list(chat)
    type_filter = MSG_TYPE_FILTERS[msg_type] if msg_type else None

    if len(chat_names) == 1:
        # 单聊搜索
        chat_ctx = resolve_chat_context(
            chat_names[0], app.msg_db_keys, app.cache, app.decrypted_dir
        )
        if not chat_ctx:
            raise click.ClickException(f"Chat not found: {chat_names[0]}")
        if not chat_ctx["db_path"]:
            raise click.ClickException(f"No message history found for {chat_ctx['display_name']}")
        entries, failures = collect_chat_search(
            chat_ctx,
            names,
            keyword,
            app.display_name_fn,
            start_ts=start_ts,
            end_ts=end_ts,
            candidate_limit=candidate_limit,
            msg_type_filter=type_filter,
        )
        scope = chat_ctx["display_name"]

    elif len(chat_names) > 1:
        # 多聊搜索
        resolved, unresolved, missing = resolve_chat_contexts(
            chat_names, app.msg_db_keys, app.cache, app.decrypted_dir
        )
        if not resolved:
            raise click.ClickException("No queryable chats found")
        entries = []
        failures = []
        for rc in resolved:
            e, f = collect_chat_search(
                rc,
                names,
                keyword,
                app.display_name_fn,
                start_ts=start_ts,
                end_ts=end_ts,
                candidate_limit=candidate_limit,
                msg_type_filter=type_filter,
            )
            entries.extend(e)
            failures.extend(f)
        if missing:
            failures.append("No message history: " + ", ".join(missing))
        if unresolved:
            failures.append("Not found: " + ", ".join(unresolved))
        scope = f"{len(resolved)} chats"

    else:
        # 全局搜索
        entries, failures = search_all_messages(
            app.msg_db_keys,
            app.cache,
            names,
            keyword,
            app.display_name_fn,
            start_ts=start_ts,
            end_ts=end_ts,
            candidate_limit=candidate_limit,
            msg_type_filter=type_filter,
        )
        scope = "all messages"

    paged = _page_ranked_entries(entries, limit, offset)

    if failures and fmt == "text":
        click.echo("Warning: Some message queries failed: " + "; ".join(failures), err=True)

    if fmt == "json":
        output(
            {
                "scope": scope,
                "keyword": keyword,
                "count": len(paged),
                "offset": offset,
                "limit": limit,
                "start_time": start_time or None,
                "end_time": end_time or None,
                "type": msg_type or None,
                "results": [item[1] for item in paged],
                "failures": failures if failures else None,
            },
            "json",
        )
    else:
        if not paged:
            output(f'No messages matching "{keyword}" in {scope}', "text")
            return
        header = f'Search for "{keyword}" in {scope}: {len(paged)} results (offset={offset}, limit={limit})'
        if start_time or end_time:
            header += f"\nTime range: {start_time or 'earliest'} ~ {end_time or 'latest'}"
        output(header + ":\n\n" + "\n\n".join(item[1] for item in paged), "text")
