"""Linux 初始化时仅为密钥扫描启动 sudo 子进程。"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import extract_keys


def extract_keys_for_init(db_dir, output_path):
    """扫描需要额外权限时提权，结果始终由调用用户保存。"""
    if platform.system() != "Linux":
        raise RuntimeError("wecli supports Linux only")

    from .scanner_linux import _check_permissions

    try:
        _check_permissions()
    except PermissionError:
        pass
    else:
        return extract_keys(db_dir, output_path)

    sudo = shutil.which("sudo")
    if sudo is None:
        raise RuntimeError(
            "Reading WeChat process memory requires sudo, but sudo is not installed."
        )

    print(
        "Reading WeChat process memory requires sudo. Enter your password when prompted.",
        file=sys.stderr,
        flush=True,
    )
    # -I 避免继承 PYTHONPATH/用户 site；显式加入当前包位置，支持 editable 安装。
    package_root = str(Path(__file__).resolve().parents[2])
    bootstrap = (
        "import sys; "
        f"sys.path.insert(0, {package_root!r}); "
        "from wecli.keys.elevation import scan_main; scan_main()"
    )
    result = subprocess.run(
        [sudo, "--", sys.executable, "-I", "-c", bootstrap, os.path.abspath(db_dir)],
        stdout=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "sudo key scanning failed. Check the authorization or scanning error above before retrying."
        )

    try:
        records = json.loads(result.stdout)
        if not isinstance(records, dict) or not records:
            raise ValueError("empty result")
        key_map = {entry["salt"]: entry["enc_key"] for entry in records.values()}
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("sudo key scanning returned invalid results") from exc

    # 临时文件由普通用户创建（0600），失败时保留原来的密钥文件。
    fd, temporary_path = tempfile.mkstemp(dir=os.path.dirname(output_path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(records, stream, indent=2, ensure_ascii=False)
        os.replace(temporary_path, output_path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return key_map


def scan_main():
    """sudo 子进程入口：stdout 仅传输 JSON，进度和错误输出到 stderr。"""
    from contextlib import redirect_stdout

    from .scanner_linux import extract_keys as scan

    try:
        with redirect_stdout(sys.stderr):
            # scanner 的日志使用 Python stdout；JSON 直接写入 fd 1 对应的管道。
            scan(sys.argv[1], "/dev/stdout")
    except Exception as exc:
        print(f"Error: Key scanning failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
