# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Extract database keys and create the wecli configuration."""

import os
import sys
from contextlib import redirect_stdout

import click

from ..core.config import (
    CONFIG_FILE,
    KEYS_FILE,
    atomic_write_json,
    auto_detect_db_dir,
    read_config,
)


@click.command()
@click.option(
    "--db-dir",
    type=click.Path(exists=True, file_okay=False),
    help="WeChat database directory (auto-detected by default)",
)
@click.option("--force", is_flag=True, help="Extract keys again even if already initialized")
@click.pass_context
def init(ctx, db_dir, force):
    """Extract database keys and create the wecli configuration.

    Use --db-dir when multiple accounts are present. Existing configuration
    fields are preserved; --force refreshes keys.
    """
    config_path = os.path.abspath(os.path.expanduser(ctx.obj or CONFIG_FILE))
    state_dir = os.path.dirname(config_path)
    try:
        cfg = read_config(config_path)
        keys_file = cfg.get("keys_file", KEYS_FILE if not ctx.obj else "all_keys.json")
        keys_file = os.path.expanduser(keys_file)
        if not os.path.isabs(keys_file):
            keys_file = os.path.join(state_dir, keys_file)
        if (
            os.path.exists(config_path)
            and os.path.exists(keys_file)
            and not force
            and db_dir is None
        ):
            click.echo(f"Already initialized (config: {config_path}). Use --force to refresh keys.")
            return
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        os.makedirs(os.path.dirname(keys_file), mode=0o700, exist_ok=True)
        if db_dir is None and cfg.get("db_dir"):
            db_dir = os.path.expanduser(cfg["db_dir"])
            if not os.path.isabs(db_dir):
                db_dir = os.path.join(state_dir, db_dir)
        if db_dir is None:
            db_dir = auto_detect_db_dir()
        if db_dir is None:
            raise click.ClickException(
                "Could not detect a database directory. Run wecli init --db-dir PATH."
            )
        db_dir = os.path.abspath(os.path.expanduser(db_dir))
        if not os.path.isdir(db_dir):
            raise click.ClickException(f"Database directory not found: {db_dir}")
        click.echo(f"Extracting keys from {db_dir}...", err=True)
        from ..keys.elevation import extract_keys_for_init

        with redirect_stdout(sys.stderr):
            key_map = extract_keys_for_init(db_dir, keys_file)
        cfg["db_dir"] = db_dir
        atomic_write_json(config_path, cfg)
    except (OSError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Initialization complete. Extracted {len(key_map)} database keys.")
    click.echo(f"Config: {config_path}\nKeys: {keys_file}")
    click.echo(
        "Next: wecli sessions" if not ctx.obj else f"Next: wecli --config '{config_path}' sessions"
    )
