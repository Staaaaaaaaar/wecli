"""Exact send targets and structured local-record checks (no display-string parsing)."""

import hashlib
import sqlite3
import time
from contextlib import closing

from .contacts import _load_contacts_from, get_self_username
from .messages import decompress_content


class SendError(ValueError):
    pass


def send_contacts(app):
    """Always refresh from the configured account, not a pre-decrypted snapshot."""
    path = app.cache.get("contact/contact.db")
    if not path:
        raise SendError("无法读取当前账号联系人数据库，请检查 init 配置。")
    return _load_contacts_from(path)[1]


def resolve_recipient(query, contacts):
    if query in ("filehelper", "File Transfer", "文件传输助手"):
        if any(
            c["username"] != "filehelper"
            and any(
                name in (c["nick_name"], c["remark"])
                for name in ("File Transfer", "文件传输助手")
            )
            for c in contacts
        ):
            raise SendError(
                "其他联系人使用了 File Transfer / 文件传输助手 名称，请先修改其备注以免混淆。"
            )
        return dict(
            username="filehelper",
            nick_name="File Transfer",
            remark="",
            ui_names=["File Transfer", "文件传输助手"],
        )
    exact_id = [c for c in contacts if c["username"] == query]
    matches = exact_id or [
        c for c in contacts if query in (c["nick_name"], c["remark"])
    ]
    unique = {c["username"]: c for c in matches}
    if not unique:
        raise SendError(
            "未找到精确匹配的联系人；请先用 contacts 查询昵称、备注或 wxid。"
        )
    if len(unique) != 1:
        raise SendError("联系人重名，请指定 wxid: " + ", ".join(unique))
    contact = dict(next(iter(unique.values())))
    name = contact["remark"] or contact["nick_name"]
    if not name or name in ("Search", "搜索", "File Transfer", "文件传输助手"):
        raise SendError("该联系人没有可安全定位的显示名称，请先设置唯一备注。")
    # An ID selects a DB contact, but cannot disambiguate identical UI names.
    if any(
        c["username"] != contact["username"] and name in (c["remark"], c["nick_name"])
        for c in contacts
    ):
        raise SendError(
            "界面名称重名；即使使用 wxid 也不能安全定位，请先设置唯一备注。"
        )
    contact["ui_names"] = [name]
    return contact


class LocalReceipt:
    def __init__(self, app, username, message):
        self.app, self.username, self.message = app, username, message
        self.cutoff = int(time.time()) - 2
        self.self_username = get_self_username(app.db_dir, app.cache, app.decrypted_dir)
        self.baseline = self.records()

    def records(self):
        records = {}
        table = "Msg_" + hashlib.md5(self.username.encode()).hexdigest()
        if not self.self_username:
            return records
        for key in self.app.msg_db_keys:
            path = self.app.cache.get(key)
            if not path:
                continue
            with closing(sqlite3.connect(path)) as conn:
                if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone():
                    continue
                senders = dict(conn.execute("SELECT rowid, user_name FROM Name2Id"))
                rows = conn.execute(
                    f"SELECT local_id, create_time, real_sender_id, message_content, WCDB_CT_message_content "
                    f"FROM [{table}] WHERE create_time >= ? AND (local_type & 4294967295) = 1 "
                    "ORDER BY create_time DESC LIMIT 200",
                    (self.cutoff,),
                )
                for local_id, created, sender_id, body, ct in rows:
                    if senders.get(sender_id) != self.self_username:
                        continue
                    body = decompress_content(body, ct)
                    if (
                        "@chatroom" in self.username
                        and isinstance(body, str)
                        and body.startswith(self.self_username + ":\n")
                    ):
                        body = body[len(self.self_username) + 2 :]
                    if body == self.message:
                        records[(key, local_id)] = dict(
                            local_id=local_id, create_time=created
                        )
        return records

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            new = [v for k, v in self.records().items() if k not in self.baseline]
            if new:
                return new[0]
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.3)
