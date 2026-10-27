# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""wecli 入口"""

import click

from . import __version__ as _VERSION
from .core.context import AppContext


class CommandGroup(click.Group):
    """Translate expected operational errors into concise CLI failures."""

    def invoke(self, ctx):
        import sqlite3

        try:
            return super().invoke(ctx)
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise click.ClickException(str(exc)) from exc


class LazyAppContext:
    """Initialize data access only when a command first needs it."""

    def __init__(self, config_path):
        self.config_path = config_path
        self._app = None

    def __getattr__(self, name):
        if self._app is None:
            self._app = AppContext(self.config_path)
        return getattr(self._app, name)


@click.group(
    cls=CommandGroup,
    context_settings={
        "help_option_names": ["-h", "--help"],
        "show_default": True,
    },
)
@click.version_option(version=_VERSION, prog_name="wecli")
@click.option(
    "--config",
    "config_path",
    default=None,
    envvar="WECLI_CONFIG",
    type=click.Path(dir_okay=False),
    help="Path to config.json (overrides WECLI_CONFIG and the default location).",
)
@click.pass_context
def cli(ctx, config_path):
    """Query local WeChat data and send text through the desktop client.

    Results use readable text by default. Use --format json for scripts.

    \b
    Examples:
      wecli launch
      wecli doctor
      wecli init
      wecli sessions
      wecli history Alice --limit 20
      wecli sessions --format json
      wecli send filehelper "Hello" --dry-run

    Bash completion: eval "$(_WECLI_COMPLETE=bash_source wecli)"
    """
    if ctx.invoked_subcommand in ("send", "doctor", "launch", "moments", "init"):
        ctx.obj = config_path
    else:
        ctx.obj = LazyAppContext(config_path)


# 注册子命令
from .commands.contacts import contacts
from .commands.doctor import doctor
from .commands.export import export
from .commands.favorites import favorites
from .commands.history import history
from .commands.init import init
from .commands.launch import launch
from .commands.members import members
from .commands.moments import moments
from .commands.new_messages import new_messages
from .commands.search import search
from .commands.send import send
from .commands.send_status import send_status
from .commands.sessions import sessions
from .commands.stats import stats
from .commands.unread import unread

cli.add_command(doctor)
cli.add_command(launch)
cli.add_command(send)
cli.add_command(send_status)
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
cli.add_command(moments)


if __name__ == "__main__":
    cli()
