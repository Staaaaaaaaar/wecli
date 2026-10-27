"""Verify the retained Linux discovery and scanner entry points."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wecli.core.config import auto_detect_db_dir, load_config
from wecli.keys import extract_keys


class LinuxScopeTests(unittest.TestCase):
    def test_native_and_legacy_discovery_and_defaults(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"HOME": directory}),
        ):
            with patch.dict(os.environ):
                os.environ.pop("SUDO_USER", None)
                native = Path(directory) / "Documents/xwechat_files/account/db_storage"
                native.mkdir(parents=True)
                legacy = Path(directory) / ".local/share/weixin/data/db_storage"
                legacy.mkdir(parents=True)
                os.utime(native, (200, 200))
                os.utime(legacy, (100, 100))
                with patch("wecli.core.config.sys.stdin.isatty", return_value=False):
                    with self.assertRaisesRegex(ValueError, "Multiple WeChat"):
                        auto_detect_db_dir()
                    legacy.rmdir()
                    self.assertEqual(auto_detect_db_dir(), str(native))
                    (Path(directory) / "config.json").write_text("{}")
                    cfg = load_config(str(Path(directory) / "config.json"))
                    self.assertEqual(cfg["wechat_process"], "wechat")
                    native.rmdir()
                    legacy.mkdir(parents=True)
                    self.assertEqual(auto_detect_db_dir(), str(legacy))

    def test_scanner_forwards_pid_and_rejects_unsupported_platform(self):
        with (
            patch("wecli.keys.platform.system", return_value="Linux"),
            patch("wecli.keys.scanner_linux.extract_keys", return_value={"salt": "key"}) as scan,
        ):
            self.assertEqual(extract_keys("db", "keys", pid=123), {"salt": "key"})
            scan.assert_called_once_with("db", "keys", pid=123)
        with (
            patch("wecli.keys.platform.system", return_value="Unsupported"),
            patch("wecli.keys.scanner_linux.extract_keys") as scan,
        ):
            with self.assertRaisesRegex(RuntimeError, "supports Linux only"):
                extract_keys("db", "keys")
            scan.assert_not_called()
