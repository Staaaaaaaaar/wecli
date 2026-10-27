# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""密钥提取模块 — 调用 Linux 内存扫描器"""

import platform


def extract_keys(db_dir, output_path, pid=None):
    """提取微信数据库密钥并保存到 output_path。

    Args:
        db_dir: 微信数据库目录（db_storage）
        output_path: all_keys.json 输出路径
        pid: 可选，指定微信进程 PID（默认自动检测）

    Returns:
        dict: salt_hex -> enc_key_hex 的映射

    Raises:
        RuntimeError: 提取失败
    """
    if platform.system() != "Linux":
        raise RuntimeError("wecli supports Linux only")
    from .scanner_linux import extract_keys as _extract

    return _extract(db_dir, output_path, pid=pid)
