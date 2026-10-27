"""CLI contracts exercised without accessing real WeChat data or the desktop."""

import importlib
import io
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import click
from click.testing import CliRunner

from wecli.core.config import atomic_write_json, load_config
from wecli.main import cli
from wecli.output.formatter import output, table


class CliContractTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_every_help_and_version_work_without_configuration(self):
        with patch("wecli.main.AppContext") as app:
            for name, command in cli.commands.items():
                paths = [[name]]
                if isinstance(command, click.Group):
                    paths += [[name, sub] for sub in command.commands]
                for path in paths:
                    for flag in ("--help", "-h"):
                        result = self.runner.invoke(
                            cli, ["--config", "/missing/config.json"] + path + [flag]
                        )
                        self.assertEqual(result.exit_code, 0, result.output)
                        self.assertIn("Usage:", result.stdout)
                        self.assertNotRegex(result.stdout, r"[\u4e00-\u9fff]")
            self.assertEqual(self.runner.invoke(cli, ["--version"]).exit_code, 0)
            app.assert_not_called()

    def test_invalid_parameters_fail_before_database_access(self):
        cases = [
            ["sessions", "--limit", "0"],
            ["unread", "--limit", "-1"],
            ["contacts", "--limit", "-1"],
            ["favorites", "--limit", "0"],
            ["history", "Alice", "--offset", "-1"],
            ["search", "x", "--limit", "501"],
            ["search", " "],
            ["history", "Alice", "--start-time", "invalid"],
            ["stats", "Alice", "--start-time", "2026-02-30"],
            ["export", "Alice", "--start-time", "2026-02-02", "--end-time", "2026-01-01"],
            ["moments", "list", "--before", "invalid"],
            ["moments", "show", str(1 << 65)],
        ]
        with (
            patch("wecli.main.AppContext") as app,
            patch("wecli.commands.moments.AppContext") as moments_app,
        ):
            for args in cases:
                result = self.runner.invoke(cli, args)
                self.assertEqual(result.exit_code, 2, (args, result.output))
                self.assertEqual(result.stdout, "")
            app.assert_not_called()
            moments_app.assert_not_called()

    def test_config_errors_are_concise_and_stay_on_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            for content in ("{broken", "[]", '{"db_dir": 123}'):
                config.write_text(content)
                result = self.runner.invoke(
                    cli, ["--config", str(config), "contacts", "--format", "json"]
                )
                self.assertEqual(result.exit_code, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("Error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
            result = self.runner.invoke(cli, ["--config", str(config) + ".missing", "contacts"])
            self.assertEqual(result.exit_code, 1)
            self.assertIn("Configuration file not found", result.stderr)

    def test_contacts_default_text_explicit_json_and_empty_results(self):
        contacts = [dict(username="wxid_a", nick_name="张三", remark="同事")]
        with (
            patch("wecli.main.AppContext"),
            patch("wecli.commands.contacts.get_contact_full", return_value=contacts),
        ):
            text = self.runner.invoke(cli, ["contacts"])
            self.assertEqual(text.exit_code, 0, text.output)
            self.assertIn("USERNAME", text.stdout)
            self.assertIn("同事", text.stdout)
            self.assertEqual(text.stderr, "")
            data = self.runner.invoke(cli, ["contacts", "--format", "json"])
            self.assertEqual(json.loads(data.stdout), contacts)
            self.assertEqual(data.stderr, "")
            empty = self.runner.invoke(cli, ["contacts", "--query", "absent"])
            self.assertEqual(empty.exit_code, 0)
            self.assertIn("No contacts found.", empty.stdout)

    def test_missing_contact_is_failure_and_members_text_handles_empty_group(self):
        with (
            patch("wecli.main.AppContext"),
            patch("wecli.commands.contacts.resolve_username", return_value="missing"),
            patch("wecli.commands.contacts.get_contact_detail", return_value=None),
        ):
            result = self.runner.invoke(cli, ["contacts", "--detail", "missing"])
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("Error: Contact not found", result.stderr)
        with (
            patch("wecli.main.AppContext"),
            patch("wecli.commands.members.resolve_username", return_value="group@chatroom"),
            patch("wecli.commands.members.get_contact_names", return_value={}),
            patch("wecli.commands.members.get_group_members") as members,
        ):
            for entries in ([], [dict(display_name="张三", username="wxid_a", remark="同事")]):
                members.return_value = dict(owner="", members=entries)
                result = self.runner.invoke(cli, ["members", "Group"])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("No members found." if not entries else "张三", result.stdout)

    def test_init_uses_selected_config_preserves_fields_and_separates_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "db"
            db.mkdir()
            config = root / "alternate/config.json"
            config.parent.mkdir()
            config.write_text(
                json.dumps(dict(db_dir=str(db), keys_file="keys/custom.json", custom="keep"))
            )

            def scan(db_dir, keys_file):
                self.assertEqual(db_dir, str(db))
                self.assertEqual(keys_file, str(config.parent / "keys/custom.json"))
                print("Scanning progress")
                atomic_write_json(keys_file, {"test": "key"})
                return {"salt": "key"}

            with patch("wecli.keys.elevation.extract_keys_for_init", side_effect=scan):
                result = self.runner.invoke(cli, ["--config", str(config), "init", "--force"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn("Scanning progress", result.stdout)
            self.assertIn("Scanning progress", result.stderr)
            self.assertEqual(json.loads(config.read_text())["custom"], "keep")
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertIn("Initialization complete", result.stdout)

    def test_config_flag_overrides_environment_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "db").mkdir()
            config = root / "config.json"
            config.write_text('{"db_dir":"db"}')
            self.assertEqual(load_config(str(config))["db_dir"], str(root / "db"))
            with patch("wecli.main.AppContext") as app:
                app.return_value.cache.get.return_value = None
                self.runner.invoke(
                    cli, ["--config", str(config), "sessions"], env={"WECLI_CONFIG": "/other"}
                )
                app.assert_called_once_with(str(config))
            with patch("wecli.main.AppContext") as app:
                app.return_value.cache.get.return_value = None
                self.runner.invoke(cli, ["sessions"], env={"WECLI_CONFIG": str(config)})
                app.assert_called_once_with(str(config))

    def test_text_formatter_never_falls_back_to_json_and_bounds_table_cells(self):
        stream = io.StringIO()
        output({"media": [{"url": "example", "available": True}]}, file=stream)
        self.assertIn("Available: Yes", stream.getvalue())
        self.assertNotIn("{", stream.getvalue())
        rendered = table(["NAME", "MESSAGE"], [("张三", "hello\n\x1b[31m" + "x" * 50)], [10, 20])
        self.assertEqual(len(rendered.splitlines()), 2)
        self.assertNotIn("\x1b", rendered)
        self.assertIn("…", rendered)

    def test_send_noninteractive_requires_yes_and_default_preview_is_text(self):
        with (
            patch("wecli.commands.send.AppContext"),
            patch("wecli.commands.send.send_contacts", return_value=[]),
            patch("wecli.commands.send.AtspiDesktop") as desktop,
        ):
            result = self.runner.invoke(cli, ["send", "filehelper", "你好"])
            self.assertEqual(result.exit_code, 2)
            self.assertIn("--yes", result.stderr)
            desktop.assert_not_called()
            result = self.runner.invoke(cli, ["send", "filehelper", "你好", "--dry-run"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("你好", result.stdout)
            self.assertNotIn("{", result.stdout)

    def test_key_scan_diagnostics_do_not_print_secret_key(self):
        from wecli.keys.common import scan_memory_for_keys

        key = "ab" * 32
        salt = "cd" * 16
        key_map = {}
        logs = []
        with patch("wecli.keys.common.verify_enc_key", return_value=True):
            scan_memory_for_keys(
                (key + salt).encode(),
                re.compile(rb"([a-f0-9]{96})"),
                [("message/test.db", "unused", 4096, salt, b"page")],
                {salt: ["message/test.db"]},
                key_map,
                {salt},
                0,
                1,
                logs.append,
            )
        self.assertEqual(key_map[salt], key)
        self.assertNotIn(key, "\n".join(logs))
        self.assertIn("message/test.db", "\n".join(logs))

    def test_summary_snapshot_is_per_account_and_not_advanced_on_output_failure(self):
        module = importlib.import_module("wecli.commands.new_messages")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "session.db"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    "CREATE TABLE SessionTable(username, unread_count, summary, last_timestamp, last_msg_type, last_msg_sender, last_sender_display_name)"
                )
                conn.execute(
                    "INSERT INTO SessionTable VALUES (?,?,?,?,?,?,?)",
                    ("a", 1, "你好", 100, 1, "", ""),
                )
            cache = SimpleNamespace(get=lambda _: str(path))
            app = SimpleNamespace(
                cache=cache,
                decrypted_dir=directory,
                db_dir=str(root / "account_a"),
                keys_file=str(root / "all_keys.json"),
            )
            with (
                patch("wecli.main.AppContext", return_value=app),
                patch.object(module, "get_contact_names", return_value={}),
            ):
                first = self.runner.invoke(cli, ["new-messages", "--format", "json"])
                self.assertTrue(json.loads(first.stdout)["first_call"])
                snapshots = list(root.glob("last_check_*.json"))
                self.assertEqual(len(snapshots), 1)
                saved = snapshots[0].read_text()
                with sqlite3.connect(path) as conn:
                    conn.execute("UPDATE SessionTable SET last_timestamp=200")
                with patch.object(module, "output", side_effect=BrokenPipeError):
                    self.runner.invoke(cli, ["new-messages"])
                self.assertEqual(snapshots[0].read_text(), saved)
                app.db_dir = str(root / "account_b")
                second = self.runner.invoke(cli, ["new-messages", "--format", "json"])
                self.assertTrue(json.loads(second.stdout)["first_call"])
                self.assertEqual(len(list(root.glob("last_check_*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
