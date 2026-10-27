# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""wecli 入口"""

import sys

import click

from .core.context import AppContext

_VERSION = "0.1.0"


@click.group()
@click.version_option(version=_VERSION, prog_name="wecli")
@click.option(
    "--config",
    "config_path",
    default=None,
    envvar="WECLI_CONFIG",
    help="config.json 路径（默认自动查找）",
)
@click.pass_context
def cli(ctx, config_path):
    """wecli — 查询微信数据，通过桌面客户端发送文本

    \b
    使用示例:
      wecli launch                              # 启用辅助功能并启动微信
      wecli doctor                              # 检查桌面环境
      wecli init                                # 首次使用：提取密钥
      wecli sessions                            # 最近会话列表
      wecli sessions --limit 10                 # 最近 10 个会话
      wecli history "张三" --limit 20          # 查看张三的最近 20 条消息
      wecli history "AI交流群" --start-time "2026-04-01"  # 指定时间范围
      wecli search "项目" --chat "AI交流群"   # 在指定群里搜索关键词
      wecli search "你好" --limit 50           # 全局搜索
      wecli contacts --query "李"              # 搜索联系人
      wecli new-messages                       # 获取增量新消息
      wecli send filehelper "你好" --yes       # 通过 AT-SPI 发送文本
    """
    # Desktop setup and send help do not require database initialization.
    if ctx.invoked_subcommand in ("send", "doctor", "launch"):
        ctx.obj = config_path
        return

    # init/version 命令不需要 AppContext
    if ctx.invoked_subcommand in ("init", "version"):
        return

    try:
        ctx.obj = AppContext(config_path)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"初始化失败: {e}", err=True)
        sys.exit(1)


# 注册子命令
from .commands.contacts import contacts
from .commands.doctor import doctor
from .commands.export import export
from .commands.favorites import favorites
from .commands.history import history
from .commands.init import init
from .commands.launch import launch
from .commands.members import members
from .commands.new_messages import new_messages
from .commands.search import search
from .commands.send import send
from .commands.sessions import sessions
from .commands.stats import stats
from .commands.unread import unread

cli.add_command(doctor)
cli.add_command(launch)
cli.add_command(send)
cli.add_command(init)
cli.add_command(sessions)
cli.add_command(history)
cli.add_command(search)
cli.add_command(contacts)
cli.add_command(new_messages)
cli.add_command(members)
cli.add_command(export)
cli.add_command(stats)
cli.add_command(unread)
cli.add_command(favorites)


if __name__ == "__main__":
    cli()
