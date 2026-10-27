import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from wecli.commands.launch import start_wechat
from wecli.core.desktop import DesktopError
from wecli.core.runtime import (
    RuntimeErrorDetail,
    clean_wechat_env,
    desktop_tool,
    worker_environment,
)
from wecli.main import cli


class RuntimeTests(unittest.TestCase):
    def test_conda_tool_wins_over_path(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            (prefix / "conda-meta").mkdir()
            (prefix / "bin").mkdir()
            tool = prefix / "bin" / "xdotool"
            tool.write_text("#!/bin/sh\n")
            tool.chmod(0o700)
            with (
                patch("wecli.core.runtime.sys.prefix", directory),
                patch("wecli.core.runtime.shutil.which") as which,
            ):
                self.assertEqual(desktop_tool("xdotool"), str(tool))
                which.assert_not_called()

    def test_missing_conda_tool_never_falls_back_to_system(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "conda-meta").mkdir()
            with (
                patch("wecli.core.runtime.sys.prefix", directory),
                patch("wecli.core.runtime.shutil.which", return_value="/usr/bin/xdotool") as which,
            ):
                with self.assertRaises(RuntimeErrorDetail):
                    desktop_tool("xdotool")
                which.assert_not_called()

    def test_conda_tool_symlink_cannot_escape_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "env"
            (prefix / "conda-meta").mkdir(parents=True)
            (prefix / "bin").mkdir()
            external = root / "system-tool"
            external.write_text("")
            external.chmod(0o700)
            (prefix / "bin/xdotool").symlink_to(external)
            with patch("wecli.core.runtime.sys.prefix", str(prefix)):
                with self.assertRaisesRegex(
                    RuntimeErrorDetail, "outside the active Conda environment"
                ):
                    desktop_tool("xdotool")

    def test_worker_uses_own_typelibs_and_keeps_desktop_bus(self):
        with (
            patch("wecli.core.runtime.in_conda", return_value=True),
            patch("wecli.core.runtime.sys.prefix", "/env/wecli"),
            patch.dict(
                os.environ,
                {
                    "DISPLAY": ":1",
                    "DBUS_SESSION_BUS_ADDRESS": "bus",
                    "GI_TYPELIB_PATH": "/other/typelibs",
                    "LD_LIBRARY_PATH": "/other/lib",
                },
            ),
        ):
            result = worker_environment()
            self.assertEqual(result["GI_TYPELIB_PATH"], "/env/wecli/lib/girepository-1.0")
            self.assertNotIn("LD_LIBRARY_PATH", result)
            self.assertEqual(result["DBUS_SESSION_BUS_ADDRESS"], "bus")
            self.assertEqual(result["DISPLAY"], ":1")

    def test_official_app_env_keeps_desktop_and_removes_conda_injection(self):
        source = dict(
            PATH="/test/conda/envs/wecli/bin:/test/conda/bin:/usr/bin:/bin",
            CONDA_PREFIX="/test/conda/envs/wecli",
            CONDA_PREFIX_1="/test/conda",
            LD_LIBRARY_PATH="/test/conda/lib",
            LD_PRELOAD="/tmp/injected.so",
            PYTHONPATH="/test/modules",
            QT_PLUGIN_PATH="/test/plugins",
            GI_TYPELIB_PATH="/test/typelibs",
            GSETTINGS_SCHEMA_DIR="/test/schemas",
            DISPLAY=":1",
            DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus",
            XAUTHORITY="/home/user/.Xauthority",
            QT_IM_MODULE="ibus",
            GDK_SCALE="2",
            XDG_DATA_DIRS="/test/conda/share:/usr/local/share:/usr/share",
        )
        result = clean_wechat_env(source)
        self.assertEqual(result["PATH"], "/usr/bin:/bin")
        self.assertEqual(result["XDG_DATA_DIRS"], "/usr/local/share:/usr/share")
        for key in (
            "CONDA_PREFIX",
            "CONDA_PREFIX_1",
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
            "PYTHONPATH",
            "QT_PLUGIN_PATH",
            "GI_TYPELIB_PATH",
            "GSETTINGS_SCHEMA_DIR",
        ):
            self.assertNotIn(key, result)
            self.assertIn(key, source)
        for key in (
            "DISPLAY",
            "DBUS_SESSION_BUS_ADDRESS",
            "XAUTHORITY",
            "QT_IM_MODULE",
            "GDK_SCALE",
        ):
            self.assertEqual(result[key], source[key])
        self.assertEqual(result["QT_ACCESSIBILITY"], "1")
        self.assertEqual(result["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"], "1")


class SetupCommandTests(unittest.TestCase):
    def test_setup_help_does_not_initialize_database(self):
        with patch("wecli.main.AppContext") as app:
            for command in ("doctor", "launch"):
                result = CliRunner().invoke(cli, [command, "--help"])
                self.assertEqual(result.exit_code, 0, result.output)
            app.assert_not_called()

    def test_doctor_reports_mixed_dependencies_as_not_ready(self):
        with (
            patch("wecli.commands.doctor.in_conda", return_value=True),
            patch("wecli.commands.doctor.AtspiDesktop") as desktop,
        ):
            desktop.return_value.inspect.return_value = dict(
                status="ready", dependencies_in_prefix=False
            )
            result = CliRunner().invoke(cli, ["doctor", "--format", "json"])
            self.assertEqual(result.exit_code, 1, result.output)
            self.assertFalse(json.loads(result.output)["ready"])

    def test_doctor_missing_desktop_is_read_only_failure(self):
        with (
            patch("wecli.commands.doctor.AtspiDesktop") as desktop,
            patch("wecli.main.AppContext") as app,
        ):
            desktop.return_value.inspect.return_value = dict(status="not_ready", error="no desktop")
            result = CliRunner().invoke(cli, ["doctor", "--format", "json"])
            self.assertEqual(result.exit_code, 1)
            app.assert_not_called()

    def test_launch_reuses_ready_instance_without_restarting(self):
        with (
            patch("wecli.commands.launch.wechat_processes", return_value=[42]),
            patch("wecli.commands.launch.AtspiDesktop") as desktop,
            patch("wecli.commands.launch.subprocess.Popen") as popen,
            patch("wecli.commands.launch.os.kill") as kill,
        ):
            desktop.return_value.inspect.return_value = dict(status="ready")
            self.assertEqual(start_wechat(Path("/usr/bin/wechat"))["status"], "already_running")
            popen.assert_not_called()
            kill.assert_not_called()

    def test_launch_leaves_existing_login_screen_to_user(self):
        with (
            patch("wecli.commands.launch.wechat_processes", return_value=[42]),
            patch("wecli.commands.launch.AtspiDesktop") as desktop,
            patch("wecli.commands.launch.subprocess.Popen") as popen,
            patch("wecli.commands.launch.os.kill") as kill,
        ):
            desktop.return_value.inspect.return_value = dict(
                status="not_ready", wechat_apps=[dict(pid=42, database_roots=[])]
            )
            report = start_wechat(Path("/usr/bin/wechat"))
            self.assertEqual(report["status"], "awaiting_login")
            self.assertFalse(report["atspi_ready"])
            kill.assert_not_called()
            popen.assert_not_called()
            desktop.return_value.send_text.assert_not_called()

    def test_launch_does_not_silently_restart_unready_instance(self):
        with (
            patch("wecli.commands.launch.wechat_processes", return_value=[42]),
            patch("wecli.commands.launch.AtspiDesktop") as desktop,
            patch("wecli.commands.launch.os.kill") as kill,
        ):
            desktop.return_value.inspect.return_value = dict(status="not_ready")
            with self.assertRaisesRegex(DesktopError, "--restart"):
                start_wechat(Path("/usr/bin/wechat"))
            kill.assert_not_called()

    def test_launch_uses_clean_env_accessibility_and_private_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "wechat"
            exe.write_text("#!/bin/sh\n")
            exe.chmod(0o700)
            with (
                patch("wecli.commands.launch.wechat_processes", return_value=[]),
                patch("wecli.commands.launch.Path.home", return_value=root),
                patch.dict(
                    os.environ,
                    {
                        "DISPLAY": ":1",
                        "XDG_SESSION_TYPE": "x11",
                        "LD_LIBRARY_PATH": "/bad",
                    },
                ),
                patch("wecli.commands.launch.subprocess.Popen") as popen,
                patch("wecli.commands.launch.time.sleep"),
            ):
                popen.return_value.pid = 99
                popen.return_value.poll.return_value = None
                result = start_wechat(exe)
                self.assertEqual(result["status"], "started")
                env = popen.call_args.kwargs["env"]
                self.assertNotIn("LD_LIBRARY_PATH", env)
                self.assertEqual(env["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"], "1")
                self.assertEqual((root / ".wecli/wechat.log").stat().st_mode & 0o777, 0o600)

    def test_restart_timeout_never_kills_forcefully_or_starts_second_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "wechat"
            exe.write_text("")
            exe.chmod(0o700)
            with (
                patch.dict(os.environ, {"DISPLAY": ":1", "XDG_SESSION_TYPE": "x11"}),
                patch("wecli.commands.launch.wechat_processes", return_value=[42]),
                patch("wecli.commands.launch.os.kill") as kill,
                patch("wecli.commands.launch.time.monotonic", side_effect=[0, 11]),
                patch("wecli.commands.launch.subprocess.Popen") as popen,
            ):
                with self.assertRaisesRegex(DesktopError, "without forcibly killing"):
                    start_wechat(exe, restart=True)
                import signal

                kill.assert_called_once_with(42, signal.SIGTERM)
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
