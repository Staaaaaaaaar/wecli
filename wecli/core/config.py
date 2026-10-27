# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""配置加载 — 从 ~/.wecli/ 读取自包含配置"""

import glob as glob_mod
import json
import os
import sys

_DEFAULT_PROCESS = "wechat"

# CLI 状态目录
STATE_DIR = os.path.expanduser("~/.wecli")
CONFIG_FILE = os.path.join(STATE_DIR, "config.json")
KEYS_FILE = os.path.join(STATE_DIR, "all_keys.json")


def _choose_candidate(candidates):
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    if not sys.stdin.isatty():
        raise ValueError(
            "Multiple WeChat database directories found. Run wecli init --db-dir PATH "
            "or specify a configuration with --config."
        )
    import click

    click.echo("Multiple WeChat database directories found:", err=True)
    for index, candidate in enumerate(candidates, 1):
        click.echo(f"  {index}. {candidate}", err=True)
    choice = click.prompt(
        "Select a directory (0 to cancel)",
        type=click.IntRange(0, len(candidates)),
        default=0,
        err=True,
    )
    return candidates[choice - 1] if choice else None


def read_config(config_path, *, required=False):
    """Read a configuration object; never silently discard invalid content."""
    if not os.path.exists(config_path):
        if required:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        return {}
    try:
        with open(config_path, encoding="utf-8") as stream:
            config = json.load(stream)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid configuration file: {config_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a JSON object: {config_path}")
    for key in ("db_dir", "keys_file", "decrypted_dir", "decoded_image_dir", "wechat_process"):
        if key in config and (not isinstance(config[key], str) or not config[key].strip()):
            raise ValueError(f"Configuration field {key} must be a non-empty string: {config_path}")
    return config


def atomic_write_json(path, data):
    """Replace a private JSON file atomically, preserving the old file on failure."""
    import tempfile

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def auto_detect_db_dir():
    """查找原生 Linux 微信的数据目录。"""
    seen = set()
    candidates = []
    search_roots = [os.path.expanduser("~/Documents/xwechat_files")]
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd

        try:
            sudo_home = pwd.getpwnam(sudo_user).pw_dir
        except KeyError:
            sudo_home = None
        if sudo_home:
            fallback = os.path.join(sudo_home, "Documents", "xwechat_files")
            if fallback not in search_roots:
                search_roots.append(fallback)
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        pattern = os.path.join(root, "*", "db_storage")
        for match in glob_mod.glob(pattern):
            normalized = os.path.normcase(os.path.normpath(match))
            if os.path.isdir(match) and normalized not in seen:
                seen.add(normalized)
                candidates.append(match)
    old_path = os.path.expanduser("~/.local/share/weixin/data/db_storage")
    if os.path.isdir(old_path):
        normalized = os.path.normcase(os.path.normpath(old_path))
        if normalized not in seen:
            candidates.append(old_path)

    def _mtime(path):
        msg_dir = os.path.join(path, "message")
        target = msg_dir if os.path.isdir(msg_dir) else path
        try:
            return os.path.getmtime(target)
        except OSError:
            return 0

    candidates.sort(key=_mtime, reverse=True)
    return _choose_candidate(candidates)


def load_config(config_path=None):
    """加载配置。默认从 ~/.wecli/config.json 读取。"""
    explicit = config_path is not None
    config_path = os.path.abspath(os.path.expanduser(config_path or CONFIG_FILE))
    cfg = read_config(config_path, required=explicit)

    # db_dir 缺失时，自动检测
    db_dir = cfg.get("db_dir", "")
    if not db_dir:
        detected = auto_detect_db_dir()
        if detected:
            cfg["db_dir"] = detected
        else:
            raise FileNotFoundError("WeChat database directory not found.\nRun: wecli init")

    # 设置默认值
    state_dir = os.path.dirname(os.path.abspath(config_path))
    cfg.setdefault("keys_file", os.path.join(state_dir, "all_keys.json"))
    cfg.setdefault("decrypted_dir", os.path.join(state_dir, "decrypted"))
    cfg.setdefault("decoded_image_dir", os.path.join(state_dir, "decoded_images"))
    cfg.setdefault("wechat_process", _DEFAULT_PROCESS)

    # 所有路径确保为绝对路径
    for key in ("db_dir", "keys_file", "decrypted_dir", "decoded_image_dir"):
        if key in cfg:
            cfg[key] = os.path.expanduser(cfg[key])
            if not os.path.isabs(cfg[key]):
                cfg[key] = os.path.join(state_dir, cfg[key])

    if not os.path.isdir(cfg["db_dir"]):
        raise FileNotFoundError(f"Database directory not found: {cfg['db_dir']}")

    # 推导微信数据根目录
    db_dir = cfg.get("db_dir", "")
    if db_dir and os.path.basename(db_dir) == "db_storage":
        cfg["wechat_base_dir"] = os.path.dirname(db_dir)
    else:
        cfg["wechat_base_dir"] = db_dir

    return cfg
