"""Minimal local Moments CLI."""

import sqlite3

import click

from ..core.context import AppContext
from ..core.messages import parse_time_range
from ..core.moments import CACHE_NOTICE, MomentsReader
from ..output.formatter import output


@click.group()
def moments():
    """浏览、搜索本机缓存的朋友圈。"""


def _reader(ctx):
    if not isinstance(ctx.obj, AppContext):
        ctx.obj = AppContext(ctx.obj)
    return MomentsReader(ctx.obj)


def _emit(data, fmt):
    data['source'] = 'local_cache'
    data['notice'] = CACHE_NOTICE
    if fmt == 'json':
        output(data)
        return
    lines = [CACHE_NOTICE]
    for item in data.get('moments', [data.get('moment')] if data.get('moment') else []):
        lines.append(f"[{item['timestamp']}] {item['author']} ({item['username']})\n"
                     f"ID: {item['id']}\n{item['content']}")
        if 'media' in item:
            import json
            for field in ('location', 'media', 'likes', 'comments'):
                lines.append(f'{field}: ' + json.dumps(item[field], ensure_ascii=False))
            if item['parse_error']:
                lines.append('解析失败: ' + item['parse_error'])
    if 'count' in data:
        lines.append(f"返回 {data['count']} 条；解析失败 {data['parse_failures']} 条")
    if data.get('next_cursor'):
        lines.append('next_cursor: ' + data['next_cursor'])
    output('\n\n'.join(lines), 'text')


def query_options(fn):
    for option in reversed([
        click.option('--user', help='作者微信 ID、昵称或备注（精确匹配）'),
        click.option('--since', default='', help='起始日期 YYYY-MM-DD [HH:MM[:SS]]'),
        click.option('--until', default='', help='结束日期 YYYY-MM-DD [HH:MM[:SS]]，含当天'),
        click.option('--limit', default=20, type=click.IntRange(1, 1000), show_default=True),
        click.option('--before', help='上一页输出的 next_cursor'),
        click.option('--format', 'fmt', default='json', type=click.Choice(['json', 'text'])),
    ]):
        fn = option(fn)
    return fn


def _query(ctx, keyword=None, **options):
    fmt = options.pop('fmt')
    try:
        since, until = parse_time_range(options.pop('since'), options.pop('until'))
        data = _reader(ctx).query(keyword=keyword, since=since, until=until, **options)
        _emit(data, fmt)
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise click.ClickException(str(exc)) from exc


@moments.command('list')
@query_options
@click.pass_context
def list_moments(ctx, **options):
    """按发布时间倒序浏览朋友圈。"""
    _query(ctx, **options)


@moments.command('search')
@click.argument('keyword')
@query_options
@click.pass_context
def search_moments(ctx, keyword, **options):
    """搜索朋友圈正文（字面匹配，不搜索评论）。"""
    if not keyword.strip():
        raise click.BadParameter('关键词不能为空', param_hint='keyword')
    _query(ctx, keyword=keyword, **options)


@moments.command('show')
@click.argument('moment_id', type=int)
@click.option('--format', 'fmt', default='json', type=click.Choice(['json', 'text']))
@click.pass_context
def show_moment(ctx, moment_id, fmt):
    """查看帖子、媒体信息及缓存中的点赞评论。"""
    try:
        item = _reader(ctx).show(moment_id)
        if item is None:
            raise ValueError('本机缓存中找不到该朋友圈')
        _emit({'moment': item}, fmt)
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise click.ClickException(str(exc)) from exc
