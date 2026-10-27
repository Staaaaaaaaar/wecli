"""Service contracts against real SQLite rows and real process locks."""

import hashlib
import json
import multiprocessing
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from wecli.core.operations import operation_path, save_operation, send_lock
from wecli.core.stream import message_page
from wecli.main import cli


def hold_lock(ready, release):
    with send_lock():
        ready.set()
        release.wait(5)


def take_lock(entered):
    with send_lock():
        entered.set()


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "message.db"
        self.table = "Msg_" + hashlib.md5(b"friend").hexdigest()
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE Name2Id(user_name TEXT)")
            conn.executemany("INSERT INTO Name2Id VALUES (?)", [("friend",), ("self",)])
            conn.execute(
                f"CREATE TABLE [{self.table}] (local_id INTEGER PRIMARY KEY, local_type INTEGER, create_time INTEGER, real_sender_id INTEGER, message_content TEXT, WCDB_CT_message_content INTEGER)"
            )
        self.app = SimpleNamespace(
            db_dir=str(self.root / "self" / "db_storage"),
            decrypted_dir=str(self.root),
            keys_file=str(self.root / "keys.json"),
            msg_db_keys=["message/message_0.db"],
            cache=SimpleNamespace(get=lambda key: str(self.path)),
        )
        patcher = patch("wecli.core.stream.get_self_username", return_value="self")
        patcher.start()
        self.addCleanup(patcher.stop)

    def insert(self, first, last):
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                f"INSERT INTO [{self.table}] VALUES (?,1,100,?,?,0)",
                [(i, 2 if i % 2 else 1, f"body {i}") for i in range(first, last + 1)],
            )

    def test_same_second_burst_replay_restart_and_late_timestamp(self):
        self.insert(1, 250)
        first = message_page(self.app, limit=17)
        self.assertEqual(first, message_page(self.app, limit=17))
        records = list(first["messages"])
        cursor = first["next_cursor"]
        # Recreate consumer context: no in-memory checkpoint is required.
        app = SimpleNamespace(**vars(self.app))
        while True:
            page = message_page(app, cursor, 17)
            records.extend(page["messages"])
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual([m["local_id"] for m in records], list(range(1, 251)))
        self.assertEqual(len({m["message_id"] for m in records}), 250)
        self.assertTrue(records[0]["is_self"])
        self.assertFalse(records[1]["is_self"])
        self.assertEqual(records[0]["sender_id"], "self")
        self.assertEqual(records[0]["chat_id"], "friend")
        self.insert(251, 252)
        with sqlite3.connect(self.path) as conn:
            conn.execute(f"UPDATE [{self.table}] SET create_time=1 WHERE local_id=251")
        page = message_page(app, cursor)
        self.assertEqual([m["local_id"] for m in page["messages"]], [251, 252])

    def test_account_switch_and_database_reset_fail_closed(self):
        self.insert(1, 5)
        cursor = message_page(self.app)["next_cursor"]
        self.app.db_dir += "-other"
        with self.assertRaisesRegex(ValueError, "account changed"):
            message_page(self.app, cursor)
        self.app.db_dir = self.app.db_dir.removesuffix("-other")
        with sqlite3.connect(self.path) as conn:
            conn.execute(f"DELETE FROM [{self.table}]")
        with self.assertRaisesRegex(ValueError, "reset"):
            message_page(self.app, cursor)

    def test_unreadable_database_never_advances(self):
        self.insert(1, 2)
        cursor = message_page(self.app)["next_cursor"]
        self.app.cache.get = lambda _: None
        with self.assertRaisesRegex(ValueError, "Cannot read"):
            message_page(self.app, cursor)

    def test_unknown_attempt_is_durable_and_reconciles_without_sending(self):
        attempt = dict(
            operation_id="12345678-1234-1234-1234-123456789abc",
            status="unknown",
            recipient="friend",
            message="hello",
            baseline=[["message/message_0.db", 1]],
            cutoff=10,
            self_username="self",
        )
        save_operation(self.app, attempt)
        self.assertEqual(
            os.stat(operation_path(self.app, attempt["operation_id"])).st_mode & 0o777, 0o600
        )
        with (
            patch("wecli.main.AppContext", return_value=self.app),
            patch("wecli.commands.send_status.LocalReceipt") as receipt,
        ):
            receipt.return_value.self_username = "self"
            receipt.return_value.wait.return_value = dict(local_id=2)
            result = CliRunner().invoke(
                cli, ["send-status", attempt["operation_id"], "--reconcile"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(json.loads(result.output)["status"], "recorded")
            self.assertEqual(receipt.return_value.baseline, {("message/message_0.db", 1): None})
        with open(operation_path(self.app, attempt["operation_id"])) as stream:
            self.assertEqual(json.load(stream)["status"], "recorded")

    def test_equal_timestamps_across_accounts_never_share_decrypted_cache(self):
        from wecli.core.db_cache import DBCache

        caches = []
        for name in ("first", "second"):
            directory = self.root / name
            directory.mkdir()
            path = directory / "message.db"
            path.write_bytes(name.encode())
            os.utime(path, ns=(1000000000, 1000000000))
            cache = DBCache({"message.db": {"enc_key": "00" * 32}}, str(directory))
            caches.append(cache)
            self.addCleanup(cache.cleanup)
        with patch(
            "wecli.core.db_cache.full_decrypt",
            side_effect=lambda src, dst, key: shutil.copyfile(src, dst),
        ):
            first = caches[0].get("message.db")
            second = caches[1].get("message.db")
            self.assertNotEqual(first, second)
            self.assertEqual(Path(first).read_bytes(), b"first")
            self.assertEqual(Path(second).read_bytes(), b"second")
            self.assertEqual(os.stat(first).st_mode & 0o777, 0o600)

    def test_cross_process_operations_wait_for_receipt_lock(self):
        context = multiprocessing.get_context("spawn")
        ready, release, entered = [context.Event() for _ in range(3)]
        first = context.Process(target=hold_lock, args=(ready, release))
        second = context.Process(target=take_lock, args=(entered,))
        try:
            first.start()
            self.assertTrue(ready.wait(5))
            second.start()
            self.assertFalse(entered.wait(0.3))
            release.set()
            self.assertTrue(entered.wait(5))
            first.join(5)
            second.join(5)
            self.assertEqual(first.exitcode, 0)
            self.assertEqual(second.exitcode, 0)
        finally:
            release.set()
            for process in (first, second):
                if process.is_alive():
                    process.terminate()
                if process.pid:
                    process.join(5)
