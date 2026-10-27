# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""数据库解密 — SQLCipher 4, AES-256-CBC"""

import os
import struct

from Crypto.Cipher import AES

PAGE_SZ = 4096
KEY_SZ = 32
SALT_SZ = 16
RESERVE_SZ = 80  # IV(16) + HMAC-SHA512(64)
SQLITE_HDR = b"SQLite format 3\x00"
WAL_HEADER_SZ = 32
WAL_FRAME_HEADER_SZ = 24


def decrypt_page(enc_key, page_data, pgno):
    iv = page_data[PAGE_SZ - RESERVE_SZ : PAGE_SZ - RESERVE_SZ + 16]
    if pgno == 1:
        encrypted = page_data[SALT_SZ : PAGE_SZ - RESERVE_SZ]
        cipher = AES.new(enc_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted)
        return bytes(bytearray(SQLITE_HDR + decrypted + b"\x00" * RESERVE_SZ))
    else:
        encrypted = page_data[: PAGE_SZ - RESERVE_SZ]
        cipher = AES.new(enc_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted)
        return decrypted + b"\x00" * RESERVE_SZ


def full_decrypt(db_path, out_path, enc_key):
    file_size = os.path.getsize(db_path)
    total_pages = file_size // PAGE_SZ
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(db_path, "rb") as fin, open(out_path, "wb") as fout:
        for pgno in range(1, total_pages + 1):
            page = fin.read(PAGE_SZ)
            if len(page) < PAGE_SZ:
                if len(page) > 0:
                    page = page + b"\x00" * (PAGE_SZ - len(page))
                else:
                    break
            fout.write(decrypt_page(enc_key, page, pgno))
    return total_pages


def decrypt_wal(wal_path, out_path, enc_key):
    if not os.path.exists(wal_path):
        return 0
    wal_size = os.path.getsize(wal_path)
    if wal_size <= WAL_HEADER_SZ:
        return 0
    # Only replay a committed prefix. A complete frame can still belong to an
    # open transaction; exposing it could advance an ingestion cursor too early.
    frame_size = WAL_FRAME_HEADER_SZ + PAGE_SZ
    with open(wal_path, "rb") as wf, open(out_path, "r+b") as df:
        wal_hdr = wf.read(WAL_HEADER_SZ)
        salts = wal_hdr[16:24]
        committed_frames = 0
        committed_size = 0
        frame_count = 0
        while wf.tell() + frame_size <= wal_size:
            fh = wf.read(WAL_FRAME_HEADER_SZ)
            pgno, db_size = struct.unpack(">II", fh[:8])
            if fh[8:16] != salts or not 1 <= pgno <= 1000000:
                break
            wf.seek(PAGE_SZ, os.SEEK_CUR)
            frame_count += 1
            if db_size:
                committed_frames = frame_count
                committed_size = db_size
        wf.seek(WAL_HEADER_SZ)
        for _ in range(committed_frames):
            fh = wf.read(WAL_FRAME_HEADER_SZ)
            pgno = struct.unpack(">I", fh[:4])[0]
            ep = wf.read(PAGE_SZ)
            df.seek((pgno - 1) * PAGE_SZ)
            df.write(decrypt_page(enc_key, ep, pgno))
        if committed_frames:
            df.truncate(committed_size * PAGE_SZ)
    return committed_frames
