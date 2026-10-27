import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wecli.core.atspi_worker import (
    Adapter,
    AdapterError,
    account_matches,
    physical_point,
)
from wecli.core.desktop import AtspiDesktop, DesktopError
from wecli.core.sending import LocalReceipt, SendError, resolve_recipient
from wecli.main import cli

CONTACT = dict(username="wxid_test", nick_name="测试", remark="")


class SendTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.app = patch("wecli.commands.send.AppContext").start()
        patch("wecli.commands.send.send_contacts", return_value=[CONTACT]).start()
        patch("wecli.commands.send.save_operation").start()
        patch(
            "wecli.commands.send.operation_path",
            return_value="/tmp/wecli-test-nonexistent-operation",
        ).start()
        self.receipt_fields = None
        self.desktop = patch("wecli.commands.send.AtspiDesktop").start()
        self.receipt = patch("wecli.commands.send.LocalReceipt").start()
        self.receipt.return_value.baseline = {}
        self.receipt.return_value.cutoff = 0
        self.receipt.return_value.self_username = "wxid_self"
        self.receipt.return_value.wait.return_value = dict(local_id=123)
        self.desktop.return_value.send_text.return_value = dict(
            status="submitted", ui_confirmed=True
        )
        self.addCleanup(patch.stopall)

    def test_help_and_invalid_input_do_not_load_database(self):
        for args, code in [
            (["--help"], 0),
            (["测试"], 2),
            (["测试", " "], 2),
            (["测试", "a\x00b"], 2),
        ]:
            result = self.runner.invoke(cli, ["send"] + args)
            self.assertEqual(result.exit_code, code, result.output)
        self.app.assert_not_called()

    def test_preview_no_desktop_or_record_scan(self):
        result = self.runner.invoke(
            cli, ["send", "测试", "你好\n第二行", "--dry-run", "--format", "json"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["status"], "dry_run")
        self.desktop.assert_not_called()
        self.receipt.assert_not_called()

    def test_cancel_and_eof_never_operate_desktop(self):
        with patch("wecli.commands.send.sys") as terminal:
            terminal.stdin.isatty.return_value = True
            for answer in ("n\n", ""):
                result = self.runner.invoke(cli, ["send", "测试", "hello"], input=answer)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("Allow wecli", result.stderr)
        self.desktop.assert_not_called()

    def test_yes_has_machine_readable_record_receipt(self):
        result = self.runner.invoke(cli, ["send", "测试", "你好", "--yes", "--format", "json"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "recorded")
        self.assertTrue(data["local_record_confirmed"])
        self.desktop.return_value.send_text.assert_called_once_with(
            ["测试"], "你好", self.app.return_value.db_dir
        )

    def test_ui_only_is_unknown_without_record(self):
        self.receipt.return_value.wait.return_value = None
        result = self.runner.invoke(cli, ["send", "测试", "hello", "-y", "--format", "json"])
        self.assertEqual(result.exit_code, 3, result.output)
        self.assertEqual(json.loads(result.output)["status"], "unknown")

    def test_uncertain_result_exits_three_and_does_not_retry(self):
        self.desktop.return_value.send_text.return_value = dict(
            status="unknown", ui_confirmed=False, error="timeout"
        )
        self.receipt.return_value.wait.return_value = None
        result = self.runner.invoke(cli, ["send", "测试", "hello", "-y", "--format", "json"])
        self.assertEqual(result.exit_code, 3, result.output)
        self.assertEqual(json.loads(result.output)["status"], "unknown")
        self.desktop.return_value.send_text.assert_called_once()

    def test_operation_uuid_replays_without_second_desktop_send(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "attempt.json")

            def persist(app, result):
                Path(path).write_text(json.dumps(result))

            with (
                patch("wecli.commands.send.operation_path", return_value=path),
                patch("wecli.commands.send.save_operation", side_effect=persist),
            ):
                args = [
                    "send",
                    "wxid_test",
                    "hello",
                    "-y",
                    "--format",
                    "json",
                    "--operation-id",
                    "12345678-1234-1234-1234-123456789abc",
                ]
                first = self.runner.invoke(cli, args)
                second = self.runner.invoke(cli, args)
                self.assertEqual(first.exit_code, 0, first.output)
                self.assertEqual(first.output, second.output)
                self.desktop.return_value.send_text.assert_called_once()
                conflict = self.runner.invoke(cli, [*args[:2], "different", *args[3:]])
                self.assertEqual(conflict.exit_code, 1)
                self.desktop.return_value.send_text.assert_called_once()

    def test_new_local_record_resolves_lost_ui_response(self):
        self.desktop.return_value.send_text.return_value = dict(
            status="unknown", ui_confirmed=False, error="timeout"
        )
        result = self.runner.invoke(cli, ["send", "测试", "hello", "-y", "--format", "json"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["status"], "recorded")
        self.assertNotIn("error", json.loads(result.output))

    def test_desktop_failure_does_not_poll_or_retry(self):
        self.desktop.return_value.send_text.side_effect = DesktopError("已有草稿")
        result = self.runner.invoke(cli, ["send", "测试", "hello", "-y", "--format", "json"])
        self.assertEqual(result.exit_code, 1)
        self.receipt.return_value.wait.assert_not_called()

    def test_utf8_file_and_crlf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.txt"
            path.write_bytes("你好\r\n第二行".encode())
            result = self.runner.invoke(
                cli, ["send", "filehelper", "--file", str(path), "--dry-run", "--format", "json"]
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["message"], "你好\n第二行")

    def test_stdin_supports_noninteractive_yes(self):
        result = self.runner.invoke(
            cli,
            ["send", "filehelper", "--file", "-", "-y", "--format", "json"],
            input="你好\n第二行",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["message"], "你好\n第二行")


class RecipientTests(unittest.TestCase):
    def test_exact_only_and_unique_names(self):
        with self.assertRaisesRegex(SendError, "exact contact match"):
            resolve_recipient("测", [CONTACT])
        contacts = [CONTACT, dict(CONTACT, username="wxid_other")]
        with self.assertRaisesRegex(SendError, "Ambiguous"):
            resolve_recipient("测试", contacts)
        with self.assertRaisesRegex(SendError, "Ambiguous UI name"):
            resolve_recipient("wxid_test", contacts)

    def test_unique_remark_disambiguates(self):
        contacts = [dict(CONTACT, remark="同事A"), dict(CONTACT, username="wxid_other")]
        self.assertEqual(resolve_recipient("wxid_test", contacts)["ui_names"], ["同事A"])

    def test_filehelper_display_name_collision_rejected(self):
        with self.assertRaisesRegex(SendError, "Another contact"):
            resolve_recipient("filehelper", [dict(CONTACT, nick_name="File Transfer")])

    def test_filehelper_aliases(self):
        for name in ("filehelper", "File Transfer", "文件传输助手"):
            self.assertEqual(resolve_recipient(name, [])["username"], "filehelper")


class TransportTests(unittest.TestCase):
    @patch.dict("os.environ", {"DISPLAY": ":1", "XDG_SESSION_TYPE": "x11"})
    @patch("wecli.core.desktop.desktop_tool", return_value="/env/bin/xdotool")
    def test_unicode_payload_uses_current_isolated_python_and_environment_tool(self, which):
        with patch(
            "wecli.core.desktop.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(dict(status="submitted", ui_confirmed=True)), ""
            ),
        ) as run:
            AtspiDesktop().send_text(["测试"], "你好 $(touch nope)", "/data/db_storage")
            args = run.call_args.args[0]
            self.assertEqual(args[:2], [sys.executable, "-I"])
            self.assertEqual(
                json.loads(run.call_args.kwargs["input"])["xdotool"], "/env/bin/xdotool"
            )
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertEqual(
                json.loads(run.call_args.kwargs["input"])["message"],
                "你好 $(touch nope)",
            )

    @patch.dict("os.environ", {"DISPLAY": ":1", "XDG_SESSION_TYPE": "x11"})
    @patch("wecli.core.desktop.desktop_tool", return_value="/env/bin/xdotool")
    def test_timeout_and_crash_are_unknown_and_never_retried(self, which):
        for failure in (subprocess.TimeoutExpired("worker", 1), None):
            with (
                self.subTest(failure=failure),
                patch(
                    "wecli.core.desktop.subprocess.run",
                    side_effect=failure,
                    return_value=subprocess.CompletedProcess([], 133, "", "crash"),
                ) as run,
            ):
                response = AtspiDesktop().send_text(["测试"], "hello", "/data")
                self.assertEqual(response["status"], "unknown")
                run.assert_called_once()


class CoordinateTests(unittest.TestCase):
    def test_scale_is_dynamic(self):
        self.assertEqual(
            physical_point((100, 200, 50, 40), (0, 0, 2048, 1280), 2, (4096, 2560)),
            (250, 440),
        )
        self.assertEqual(
            physical_point((100, 200, 50, 40), (0, 0, 2048, 1280), 1, (2048, 1280)),
            (125, 220),
        )

    def test_offscreen_and_inconsistent_layout_rejected(self):
        for rect, monitor, scale, screen in [
            ((2000, 0, 100, 20), (0, 0, 2048, 1280), 2, (4096, 2560)),
            ((0, 0, 20, 20), (1920, 0, 2048, 1280), 2, (4096, 2560)),
            ((0, 0, 20, 20), (0, 0, 2048, 1280), 2, (2048, 1280)),
        ]:
            with self.assertRaises(AdapterError):
                physical_point(rect, monitor, scale, screen)

    def test_account_mismatch_rejected(self):
        self.assertFalse(account_matches(2147483647, "/different/account/db_storage"))


class SubmissionTests(unittest.TestCase):
    def make_adapter(self, draft=""):
        adapter = object.__new__(Adapter)
        adapter.message = "你好"
        adapter.attempted = False
        adapter.app = MagicMock()
        adapter.request = {"db_dir": "/data/db_storage"}
        patcher = patch("wecli.core.atspi_worker.account_matches", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        adapter.start = MagicMock()
        adapter.select_chat = MagicMock()
        field = MagicMock()
        field.get_character_count.return_value = len(draft)
        field.get_text.return_value = "你好"
        field.set_text_contents.return_value = True
        adapter.current_input = MagicMock(return_value=field)
        adapter.matching_messages = MagicMock(return_value=0)
        adapter.wait = MagicMock(return_value=MagicMock())
        adapter.focus = MagicMock()
        return adapter, field

    def test_locked_session_never_starts_desktop_operation(self):
        adapter, field = self.make_adapter()
        with patch("wecli.core.atspi_worker.screen_locked", return_value=True):
            with self.assertRaisesRegex(AdapterError, "locked"):
                adapter.submit()
        adapter.start.assert_not_called()
        self.assertFalse(adapter.attempted)

    def test_account_switch_before_click_is_rejected(self):
        adapter, field = self.make_adapter()
        adapter.click = lambda button, before_click: before_click()
        with patch("wecli.core.atspi_worker.account_matches", return_value=False):
            with self.assertRaisesRegex(AdapterError, "Account changed"):
                adapter.submit()
        self.assertFalse(adapter.attempted)

    def test_existing_draft_not_overwritten(self):
        adapter, field = self.make_adapter("existing")
        with self.assertRaisesRegex(AdapterError, "draft"):
            adapter.submit()
        field.set_text_contents.assert_not_called()
        self.assertFalse(adapter.attempted)

    def test_recipient_change_blocks_send(self):
        adapter, field = self.make_adapter()
        adapter.current_input.side_effect = [field, None]
        adapter.click = lambda button, before_click: before_click()
        with self.assertRaisesRegex(AdapterError, "Recipient"):
            adapter.submit()
        self.assertFalse(adapter.attempted)

    def test_draft_readback_failure_blocks_click(self):
        adapter, field = self.make_adapter()
        field.get_text.return_value = "wrong"
        adapter.click = MagicMock()
        with self.assertRaisesRegex(AdapterError, "readback"):
            adapter.submit()
        adapter.click.assert_not_called()

    def test_click_failure_is_marked_uncertain_and_once(self):
        adapter, field = self.make_adapter()

        def click(button, before_click):
            before_click()
            raise AdapterError("click timed out")

        adapter.click = MagicMock(side_effect=click)
        with self.assertRaises(AdapterError):
            adapter.submit()
        self.assertTrue(adapter.attempted)
        adapter.click.assert_called_once()


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "messages.db"
        self.table = "Msg_" + hashlib.md5(b"filehelper").hexdigest()
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.execute("CREATE TABLE Name2Id(user_name TEXT)")
        self.conn.executemany("INSERT INTO Name2Id VALUES (?)", [("wxid_self",), ("filehelper",)])
        self.conn.execute(
            f"CREATE TABLE [{self.table}] (local_id INTEGER, local_type INTEGER, create_time INTEGER, real_sender_id INTEGER, message_content TEXT, WCDB_CT_message_content INTEGER)"
        )
        self.app = SimpleNamespace(
            db_dir="/data/db_storage",
            cache=MagicMock(),
            decrypted_dir="/data",
            msg_db_keys=["message/message_0.db"],
        )
        self.app.cache.get.return_value = str(self.path)
        self.self_patch = patch("wecli.core.sending.get_self_username", return_value="wxid_self")
        self.self_patch.start()
        self.addCleanup(self.self_patch.stop)

    def insert(self, local_id, sender=1, body="你好"):
        import time

        self.conn.execute(
            f"INSERT INTO [{self.table}] VALUES (?,1,?,?,?,0)",
            (local_id, int(time.time()), sender, body),
        )
        self.conn.commit()

    def test_old_duplicate_or_incoming_message_is_not_confirmation(self):
        self.insert(1)
        receipt = LocalReceipt(self.app, "filehelper", "你好")
        self.insert(2, sender=2)
        self.assertIsNone(receipt.wait(0))
        self.insert(3, body="你好 extra")
        self.assertIsNone(receipt.wait(0))
        self.insert(4)
        self.assertEqual(receipt.wait(0)["local_id"], 4)


if __name__ == "__main__":
    unittest.main()
