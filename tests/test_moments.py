import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from wecli.core.moments import MomentsReader, decode_cursor, parse_moment
from wecli.main import cli


def xml(text, ts=100, extra=""):
    return (
        f"<SnsDataItem><TimelineObject><createTime>{ts}</createTime>"
        f"<contentDesc>{text}</contentDesc><ContentObject><type>1</type>"
        '<mediaList><media><url key="secret">https://example.test/image</url>'
        "</media></mediaList></ContentObject></TimelineObject>"
        f"<LocalExtraInfo><nickname>作者</nickname>{extra}</LocalExtraInfo></SnsDataItem>"
    )


class MomentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "sns"
        path.mkdir()
        with sqlite3.connect(path / "sns.db") as conn:
            conn.execute(
                "CREATE TABLE SnsTimeLine(tid INTEGER PRIMARY KEY, user_name TEXT, content TEXT)"
            )
            conn.executemany(
                "INSERT INTO SnsTimeLine VALUES(?,?,?)",
                [
                    (3, "a", xml("旅行 100%")),
                    (2, "a", xml("旅行海边")),
                    (
                        1,
                        "b",
                        xml(
                            "别的正文",
                            90,
                            "<comment_user_list><user_comment><content>旅行</content>"
                            "</user_comment></comment_user_list>",
                        ),
                    ),
                    (4, "b", "<broken"),
                ],
            )
        app = SimpleNamespace(decrypted_dir=self.tmp.name, cache=None)
        with patch(
            "wecli.core.moments.get_contact_full",
            return_value=[
                dict(username="a", nick_name="同名", remark="甲"),
                dict(username="b", nick_name="同名", remark="乙"),
            ],
        ):
            self.reader = MomentsReader(app)

    def test_tied_timestamp_cursor_and_filters(self):
        page = self.reader.query(limit=1, user="甲")
        self.assertEqual(page["moments"][0]["id"], "3")
        second = self.reader.query(limit=1, user="甲", before=page["next_cursor"])
        self.assertEqual(second["moments"][0]["id"], "2")
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(self.reader.query(since=100, until=100)["count"], 2)
        self.assertEqual(self.reader.query(keyword="100%")["count"], 1)
        self.assertEqual(self.reader.query(keyword="旅行")["count"], 2)
        self.assertEqual(self.reader.query(user="unknown")["count"], 0)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.reader.query(user="同名")

    def test_details_malformed_and_missing(self):
        item = self.reader.show(1)
        self.assertEqual(item["comments"][0]["content"], "旅行")
        self.assertEqual(item["media"][0]["url"]["key"], "secret")
        self.assertEqual(self.reader.show(4)["parse_error"], "invalid_xml")
        self.assertIsNone(self.reader.show(999))
        self.assertEqual(self.reader.query()["parse_failures"], 1)
        self.assertEqual(parse_moment(1, "a", "<other/>")["parse_error"], "missing_timeline_object")
        with self.assertRaises(ValueError):
            decode_cursor("not a cursor")

    def test_unsigned_server_id_roundtrip(self):
        with sqlite3.connect(self.reader.path) as conn:
            conn.execute("INSERT INTO SnsTimeLine VALUES(?,?,?)", (-1, "a", xml("大 ID", 101)))
        item = self.reader.query(limit=1)["moments"][0]
        self.assertEqual(item["id"], "18446744073709551615")
        self.assertEqual(self.reader.show(item["id"])["content"], "大 ID")
        with patch("wecli.commands.moments._reader", return_value=self.reader):
            result = CliRunner().invoke(cli, ["moments", "show", item["id"]])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_commands_and_validation(self):
        runner = CliRunner()
        with patch("wecli.commands.moments._reader", return_value=self.reader):
            for args in [["list", "--limit", "1"], ["search", "旅行"], ["show", "1"]]:
                result = runner.invoke(cli, ["moments"] + args + ["--format", "json"])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(json.loads(result.output)["source"], "local_cache")
            result = runner.invoke(cli, ["moments", "show", "1", "--format", "text"])
            self.assertIn("旅行", result.output)
            for args in [
                ["list", "--before", "bad"],
                ["show", "999"],
                ["list", "--since", "2026-02-30"],
                ["list", "--limit", "0"],
                ["search", " "],
                ["list", "--since", "2026-02-02", "--until", "2026-01-01"],
            ]:
                self.assertNotEqual(runner.invoke(cli, ["moments"] + args).exit_code, 0)
        with patch("wecli.main.AppContext") as app:
            for args in [
                ["moments", "--help"],
                ["moments", "list", "--help"],
                ["moments", "show", "--help"],
            ]:
                self.assertEqual(runner.invoke(cli, args).exit_code, 0)
            app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
