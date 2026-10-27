"""授权边界与初始化回归检查；不读取真实微信数据，也不调用真实 sudo。"""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from wecli.keys import elevation


RECORDS = {"message/test.db": {"salt": "ab" * 16, "enc_key": "cd" * 32}}
KEY_MAP = {"ab" * 16: "cd" * 32}


@unittest.skipUnless(sys.platform == "linux", "Linux sudo flow")
class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="wecli test ")
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "all_keys.json"
        self.output.write_text("previous keys")
        self.addCleanup(patch.stopall)
        patch("wecli.keys.elevation.platform.system", return_value="Linux").start()
        self.permissions = patch(
            "wecli.keys.scanner_linux._check_permissions", side_effect=PermissionError
        ).start()
        self.sudo = patch("wecli.keys.elevation.shutil.which", return_value="/usr/bin/sudo").start()

    def test_elevated_scan_uses_current_python_and_user_saves_keys(self):
        # 执行实际 Python 子进程，替换 sudo 和扫描器；验证 fd 1 JSON 与日志分离。
        run = subprocess.run

        def simulated_sudo(command, **kwargs):
            self.assertEqual(command[:5], ["/usr/bin/sudo", "--", sys.executable, "-I", "-c"])
            self.assertEqual(command[-1], self.directory.name)
            self.assertNotIn("env", command)
            self.assertIsNone(kwargs.get("stderr"))  # sudo 密码提示与进度实时显示
            bootstrap = command[5]
            setup = (
                "import wecli.keys.scanner_linux as scanner; "
                f"records = {RECORDS!r}; "
                "exec('def fake_scan(db_dir, output_path):\\n"
                "    print(\"scan progress\")\\n"
                "    with open(output_path, \"w\") as f:\\n"
                "        __import__(\"json\").dump(records, f)'); "
                "scanner.extract_keys = fake_scan; "
            )
            bootstrap = bootstrap.replace(
                "from wecli.keys.elevation import scan_main;", setup + "from wecli.keys.elevation import scan_main;"
            )
            result = run([sys.executable, "-I", "-c", bootstrap, command[-1]],
                         stderr=subprocess.PIPE, **kwargs)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("scan progress", result.stderr)
            return result

        with patch("wecli.keys.elevation.subprocess.run", side_effect=simulated_sudo) as child:
            keys = elevation.extract_keys_for_init(self.directory.name, str(self.output))
        self.assertEqual(keys, KEY_MAP)
        self.assertEqual(json.loads(self.output.read_text()), RECORDS)
        self.assertEqual(self.output.stat().st_uid, os.getuid())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        child.assert_called_once()

    def test_sudo_failure_preserves_existing_keys(self):
        with patch("wecli.keys.elevation.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "")):
            with self.assertRaisesRegex(RuntimeError, "sudo 密钥扫描未完成"):
                elevation.extract_keys_for_init(self.directory.name, str(self.output))
        self.assertEqual(self.output.read_text(), "previous keys")

    def test_invalid_response_preserves_existing_keys(self):
        for response in ("", "progress\n{}", "{}", "[]", '{"db": {}}'):
            with self.subTest(response=response), patch(
                "wecli.keys.elevation.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, response),
            ):
                with self.assertRaisesRegex(RuntimeError, "无效结果"):
                    elevation.extract_keys_for_init(self.directory.name, str(self.output))
                self.assertEqual(self.output.read_text(), "previous keys")

    def test_missing_sudo(self):
        self.sudo.return_value = None
        with self.assertRaisesRegex(RuntimeError, "未安装 sudo"):
            elevation.extract_keys_for_init(self.directory.name, str(self.output))

    def test_existing_permission_does_not_launch_sudo(self):
        self.permissions.side_effect = None
        with patch("wecli.keys.elevation.extract_keys", return_value=KEY_MAP) as scan:
            self.assertEqual(elevation.extract_keys_for_init("db", "keys"), KEY_MAP)
        scan.assert_called_once_with("db", "keys")
        self.sudo.assert_not_called()

    def test_unsupported_platform_rejected_before_scanning(self):
        with patch("wecli.keys.elevation.platform.system", return_value="Unsupported"), patch(
            "wecli.keys.elevation.extract_keys"
        ) as scan:
            with self.assertRaisesRegex(RuntimeError, "仅支持 Linux"):
                elevation.extract_keys_for_init("db", "keys")
        scan.assert_not_called()
        self.permissions.assert_not_called()
        self.sudo.assert_not_called()


class InitTests(unittest.TestCase):
    def test_existing_init_skips_scan_and_force_rescans(self):
        module = importlib.import_module("wecli.commands.init")
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            keys = Path(directory) / "all_keys.json"
            config.write_text("{}")
            keys.write_text("{}")
            with patch.multiple(module, STATE_DIR=directory, CONFIG_FILE=str(config), KEYS_FILE=str(keys)), patch(
                "wecli.keys.elevation.extract_keys_for_init", return_value=KEY_MAP
            ) as scan:
                runner = CliRunner()
                result = runner.invoke(module.init, [])
                self.assertEqual(result.exit_code, 0, result.output)
                scan.assert_not_called()
                result = runner.invoke(module.init, ["--force", "--db-dir", directory])
                self.assertEqual(result.exit_code, 0, result.output)
                scan.assert_called_once_with(directory, str(keys))
                self.assertEqual(json.loads(config.read_text()), {"db_dir": directory})

    def test_scan_failure_does_not_overwrite_config(self):
        module = importlib.import_module("wecli.commands.init")
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("previous config")
            with patch.multiple(module, STATE_DIR=directory, CONFIG_FILE=str(config), KEYS_FILE=str(Path(directory) / "keys")), patch(
                "wecli.keys.elevation.extract_keys_for_init", side_effect=RuntimeError("sudo cancelled")
            ):
                result = CliRunner().invoke(module.init, ["--force", "--db-dir", directory])
                self.assertEqual(result.exit_code, 1)
                self.assertIn("sudo cancelled", result.output)
                self.assertEqual(config.read_text(), "previous config")
