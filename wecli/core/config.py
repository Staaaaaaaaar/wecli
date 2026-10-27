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
    if len(candidates) > 1:
        if not sys.stdin.isatty():
            return candidates[0]
        print("[!] 检测到多个微信数据目录:")
        for i, c in enumerate(candidates, 1):
            print(f"    {i}. {c}")
        print("    0. 跳过")
        try:
            while True:
                choice = input(f"请选择 [0-{len(candidates)}]: ").strip()
                if choice == "0":
                    return None
                if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                    return candidates[int(choice) - 1]
                print("    无效输入")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
    return None


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
    if config_path is None:
        config_path = CONFIG_FILE

    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError:
            cfg = {}

    # db_dir 缺失时，自动检测
    db_dir = cfg.get("db_dir", "")
    if not db_dir:
        detected = auto_detect_db_dir()
        if detected:
            cfg["db_dir"] = detected
        else:
            raise FileNotFoundError(
                "未找到微信数据目录。\n"
                "请运行: wecli init"
            )

    # 设置默认值
    state_dir = os.path.dirname(os.path.abspath(config_path))
    cfg.setdefault("keys_file", os.path.join(state_dir, "all_keys.json"))
    cfg.setdefault("decrypted_dir", os.path.join(state_dir, "decrypted"))
    cfg.setdefault("decoded_image_dir", os.path.join(state_dir, "decoded_images"))
    cfg.setdefault("wechat_process", _DEFAULT_PROCESS)

    # 所有路径确保为绝对路径
    for key in ("db_dir", "keys_file", "decrypted_dir", "decoded_image_dir"):
        if key in cfg and not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(state_dir, cfg[key])

    # 推导微信数据根目录
    db_dir = cfg.get("db_dir", "")
    if db_dir and os.path.basename(db_dir) == "db_storage":
        cfg["wechat_base_dir"] = os.path.dirname(db_dir)
    else:
        cfg["wechat_base_dir"] = db_dir

    return cfg
