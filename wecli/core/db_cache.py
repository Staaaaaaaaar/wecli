# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Private per-process immutable snapshots, isolated by account."""

import hashlib
import os
import tempfile

from .crypto import decrypt_wal, full_decrypt
from .key_utils import get_key_info


class DBCache:
    def __init__(self, all_keys, db_dir):
        self._all_keys = all_keys
        self._db_dir = db_dir
        identity = hashlib.sha256(os.path.realpath(db_dir).encode()).hexdigest()
        self.CACHE_DIR = os.path.join(tempfile.gettempdir(), f"wecli_cache_{os.getuid()}", identity)
        os.makedirs(self.CACHE_DIR, mode=0o700, exist_ok=True)
        self._cache = {}
        self._snapshots = []

    def get(self, rel_key):
        key_info = get_key_info(self._all_keys, rel_key)
        if not key_info:
            return None
        rel_path = rel_key.replace("\\", "/").replace("/", os.sep)
        db_path = os.path.join(self._db_dir, rel_path)
        wal_path = db_path + "-wal"
        if not os.path.exists(db_path):
            return None

        try:
            db_mtime = (os.stat(db_path).st_mtime_ns, os.stat(db_path).st_size)
            wal_mtime = (
                (os.stat(wal_path).st_mtime_ns, os.stat(wal_path).st_size)
                if os.path.exists(wal_path)
                else 0
            )
        except OSError:
            return None

        if rel_key in self._cache:
            c_db_mt, c_wal_mt, c_path = self._cache[rel_key]
            if c_db_mt == db_mtime and c_wal_mt == wal_mtime and os.path.exists(c_path):
                return c_path

        fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=self.CACHE_DIR)
        os.close(fd)
        self._snapshots.append(tmp_path)
        enc_key = bytes.fromhex(key_info["enc_key"])
        full_decrypt(db_path, tmp_path, enc_key)
        if os.path.exists(wal_path):
            decrypt_wal(wal_path, tmp_path, enc_key)
        current_db = (os.stat(db_path).st_mtime_ns, os.stat(db_path).st_size)
        current_wal = (
            (os.stat(wal_path).st_mtime_ns, os.stat(wal_path).st_size)
            if os.path.exists(wal_path)
            else 0
        )
        if (current_db, current_wal) != (db_mtime, wal_mtime):
            raise ValueError(
                "WeChat database changed while taking a snapshot; retry with the same cursor"
            )
        self._cache[rel_key] = (db_mtime, wal_mtime, tmp_path)
        return tmp_path

    def cleanup(self):
        for path in self._snapshots:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
