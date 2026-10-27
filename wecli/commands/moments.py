"""Browse and search locally cached Moments."""

import sqlite3

import click

from ..core.context import AppContext
from ..core.messages import parse_time_range
from ..core.moments import CACHE_NOTICE, MomentsReader, decode_cursor
from ..output.formatter import output, readable


@click.group()
def moments():
    """Browse and search locally cached Moments."""


def _reader(ctx):
    if not isinstance(ctx.obj, AppContext):
        ctx.obj = AppContext(ctx.obj)
    return MomentsReader(ctx.obj)


def _emit(data, fmt):
    data["source"] = "local_cache"
    data["notice"] = CACHE_NOTICE
    if fmt == "json":
        output(data, "json")
        return
    lines = [CACHE_NOTICE]
    for item in data.get("moments", [data.get("moment")] if data.get("moment") else []):
        lines.append(
            f"[{item['timestamp']}] {item['author']} ({item['username']})\n"
            f"ID: {item['id']}\n{item['content']}"
        )
        if "media" in item:
            for field in ("location", "media", "likes", "comments"):
                lines.append(f"{field}: " + "\n" + readable(item[field], 2))
            if item["parse_error"]:
                lines.append("Parse failure: " + item["parse_error"])
    if "count" in data:
        lines.append(f"Returned {data['count']} moments; {data['parse_failures']} parse failures")
    if data.get("next_cursor"):
        lines.append("next_cursor: " + data["next_cursor"])
    output("\n\n".join(lines), "text")


def query_options(fn):
    for option in reversed(
        [
            click.option("--user", help="Author wxid, nickname, or remark (exact match)"),
            click.option("--since", default="", help="Start date: YYYY-MM-DD [HH:MM[:SS]]"),
            click.option(
                "--until",
                default="",
                help="End date: YYYY-MM-DD [HH:MM[:SS]] (date includes the entire day)",
            ),
            click.option("--limit", default=20, type=click.IntRange(1, 1000), show_default=True),
            click.option("--before", help="next_cursor from the previous page"),
            click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"])),
        ]
    ):
        fn = option(fn)
    return fn


def _query(ctx, keyword=None, **options):
    fmt = options.pop("fmt")
    try:
        since, until = parse_time_range(options.pop("since"), options.pop("until"))
        if options.get("before"):
            decode_cursor(options["before"])
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    try:
        data = _reader(ctx).query(keyword=keyword, since=since, until=until, **options)
        _emit(data, fmt)
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise click.ClickException(str(exc)) from exc


@moments.command("list")
@query_options
@click.pass_context
def list_moments(ctx, **options):
    """List locally cached Moments, newest first."""
    _query(ctx, **options)


@moments.command("search")
@click.argument("keyword")
@query_options
@click.pass_context
def search_moments(ctx, keyword, **options):
    """Search cached post text (literal match; excludes comments)."""
    if not keyword.strip():
        raise click.BadParameter("Keyword must not be empty", param_hint="keyword")
    _query(ctx, keyword=keyword, **options)


@moments.command("show")
@click.argument("moment_id", type=int)
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"]))
@click.pass_context
def show_moment(ctx, moment_id, fmt):
    """Show a cached post, media metadata, likes, and comments."""
    if not -(1 << 63) <= moment_id < (1 << 64):
        raise click.BadParameter("Moment ID is outside the 64-bit range", param_hint="moment_id")
    try:
        item = _reader(ctx).show(moment_id)
        if item is None:
            raise ValueError("Moment not found in the local cache")
        _emit({"moment": item}, fmt)
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise click.ClickException(str(exc)) from exc
