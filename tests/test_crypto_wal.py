"""Regression: uncommitted WAL data must never reach a message snapshot."""

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wecli.core.crypto import PAGE_SZ, decrypt_wal


class WalTests(unittest.TestCase):
    def test_only_committed_prefix_is_applied_and_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, wal = root / "plain.db", root / "encrypted.db-wal"
            target.write_bytes(b"A" * PAGE_SZ * 3)
            salt = b"12345678"
            header = b"\0" * 16 + salt + b"\0" * 8

            def frame(page, size, content, frame_salt=salt):
                return struct.pack(">II", page, size) + frame_salt + b"\0" * 8 + content * PAGE_SZ

            with patch("wecli.core.crypto.decrypt_page", side_effect=lambda key, page, pgno: page):
                wal.write_bytes(header + frame(1, 0, b"B"))
                self.assertEqual(decrypt_wal(wal, target, b""), 0)
                self.assertEqual(target.read_bytes(), b"A" * PAGE_SZ * 3)
                wal.write_bytes(header + frame(1, 0, b"B") + frame(2, 2, b"C") + frame(1, 0, b"D"))
                self.assertEqual(decrypt_wal(wal, target, b""), 2)
                self.assertEqual(target.read_bytes(), b"B" * PAGE_SZ + b"C" * PAGE_SZ)
                # Stale frames after a salt mismatch must not create a commit.
                wal.write_bytes(header + frame(1, 0, b"E") + frame(2, 2, b"F", b"87654321"))
                self.assertEqual(decrypt_wal(wal, target, b""), 0)
                self.assertEqual(target.read_bytes(), b"B" * PAGE_SZ + b"C" * PAGE_SZ)
