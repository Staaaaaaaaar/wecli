"""Read locally cached Moments without fetching remote content."""

import base64
import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path

from .contacts import get_contact_full

CACHE_NOTICE = (
    "Local cache only. History, media, likes, comments, and recent WAL changes may be incomplete."
)


def _integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_moment(tid, username, content):
    item = dict(
        id=str(tid if tid >= 0 else tid + (1 << 64)),
        username=username,
        timestamp=None,
        content="",
        nickname="",
        type=None,
        location={},
        media=[],
        likes=[],
        comments=[],
        parse_error=None,
    )
    try:
        root = ET.fromstring(content or "")
    except (ET.ParseError, ValueError, TypeError):
        item["parse_error"] = "invalid_xml"
        return item
    timeline = root if root.tag == "TimelineObject" else root.find("TimelineObject")
    if timeline is None:
        item["parse_error"] = "missing_timeline_object"
        return item
    item.update(
        timestamp=_integer(timeline.findtext("createTime")),
        content=timeline.findtext("contentDesc") or "",
        type=_integer(timeline.findtext("ContentObject/type")),
        nickname=root.findtext("LocalExtraInfo/nickname") or "",
    )
    location = timeline.find("location")
    if location is not None:
        item["location"] = dict(location.attrib)
    for node in timeline.findall("ContentObject/mediaList/media"):
        media = {}
        for name in ("id", "type", "title", "description", "videoDuration"):
            if node.find(name) is not None:
                media[name] = node.findtext(name) or ""
        for name in ("url", "thumb", "size", "enc"):
            child = node.find(name)
            if child is not None:
                media[name] = dict(child.attrib, value=child.text or "")
        item["media"].append(media)
    for field, tag in [("likes", "like_user_list"), ("comments", "comment_user_list")]:
        for node in root.findall(f"LocalExtraInfo/{tag}/user_comment"):
            item[field].append({child.tag: child.text or "" for child in node})
    return item


def encode_cursor(item):
    payload = json.dumps([item["timestamp"], item["id"]], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(value):
    try:
        data = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(data, list)
            or len(data) != 2
            or type(data[0]) is not int
            or not isinstance(data[1], str)
        ):
            raise ValueError()
        return data[0], int(data[1])
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError(
            "Invalid --before cursor. Use next_cursor from the previous page."
        ) from exc


class MomentsReader:
    def __init__(self, app):
        pre = os.path.join(app.decrypted_dir, "sns", "sns.db")
        path = pre if os.path.isfile(pre) else app.cache.get("sns/sns.db")
        if not path:
            raise ValueError(
                "Cannot access sns/sns.db. Open Moments in WeChat and run wecli init --force to refresh keys."
            )
        self.path = path
        self.contacts = get_contact_full(app.cache, app.decrypted_dir)
        self.names = {
            c["username"]: c.get("remark") or c.get("nick_name") or c["username"]
            for c in self.contacts
        }

    def _connect(self):
        return sqlite3.connect(Path(self.path).resolve().as_uri() + "?mode=ro", uri=True)

    def _parse(self, row):
        item = parse_moment(*row)
        item["author"] = self.names.get(item["username"], item["nickname"] or item["username"])
        return item

    def show(self, moment_id):
        # SQLite stores the unsigned server ID in a signed 64-bit integer.
        number = int(moment_id)
        if not -(1 << 63) <= number < (1 << 64):
            raise ValueError("Moment ID is outside the 64-bit range")
        if number >= 1 << 63:
            number -= 1 << 64
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT tid, user_name, content FROM SnsTimeLine WHERE tid = ?", (number,)
            ).fetchone()
        return self._parse(row) if row else None

    def query(self, *, limit=20, user=None, keyword=None, since=None, until=None, before=None):
        boundary = decode_cursor(before) if before else None
        with closing(self._connect()) as conn:
            items = [
                self._parse(row)
                for row in conn.execute("SELECT tid, user_name, content FROM SnsTimeLine")
            ]
        if user:
            users = {item["username"] for item in items}
            if user in users or any(c["username"] == user for c in self.contacts):
                matches = {user}
            else:
                matches = {
                    c["username"]
                    for c in self.contacts
                    if user.casefold()
                    in {c.get("nick_name", "").casefold(), c.get("remark", "").casefold()}
                }
                matches.update(
                    item["username"]
                    for item in items
                    if item["nickname"].casefold() == user.casefold()
                )
            if len(matches) > 1:
                raise ValueError("Ambiguous author name. Use a wxid: " + ", ".join(sorted(matches)))
            items = [item for item in items if item["username"] in matches]
        failures = sum(item["parse_error"] is not None for item in items)
        result = []
        for item in items:
            ts = item["timestamp"]
            if ts is None:
                continue
            if since is not None and ts < since or until is not None and ts > until:
                continue
            if keyword is not None and keyword.casefold() not in item["content"].casefold():
                continue
            if boundary is not None and (ts, int(item["id"])) >= boundary:
                continue
            result.append(item)
        result.sort(key=lambda item: (item["timestamp"], int(item["id"])), reverse=True)
        page = result[:limit]
        # Interaction and media details are available through show.
        summaries = [
            {k: v for k, v in item.items() if k not in ("likes", "comments", "media")}
            | {"media_count": len(item["media"])}
            for item in page
        ]
        return dict(
            count=len(page),
            moments=summaries,
            next_cursor=encode_cursor(page[-1]) if len(result) > limit else None,
            parse_failures=failures,
        )
