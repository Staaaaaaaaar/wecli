"""Standalone current-environment Python worker. JSON stdin/stdout; no project dependencies."""

import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class AdapterError(RuntimeError):
    pass


def physical_point(rect, monitor, scale, screen):
    """Only an unambiguous single-monitor logical -> X11 mapping is admitted."""
    mx, my, mw, mh = monitor
    if (mx, my) != (0, 0) or (mw * scale, mh * scale) != tuple(screen):
        raise AdapterError(
            "Display coordinates and scaling disagree. A single X11 display with integer scaling is required."
        )
    x, y, w, h = rect
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > mw or y + h > mh:
        raise AdapterError(
            "Target control is not fully on screen. Move the WeChat window on screen and retry."
        )
    return round((x + w / 2) * scale), round((y + h / 2) * scale)


def account_matches(pid, expected):
    expected = str(Path(expected).resolve()) + os.sep
    try:
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                if os.readlink(fd).startswith(expected):
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


class Adapter:
    def __init__(self, request):
        import gi

        gi.require_version("Atspi", "2.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Atspi, Gdk, GLib

        self.A, self.G, self.GLib = Atspi, Gdk, GLib
        Atspi.set_timeout(1000, 1000)
        self.request = request
        self.names = request["names"]
        self.message = request["message"]
        self.timeout = request["timeout"]
        self.attempted = False
        self.origin = None
        self.window = None
        self.app = None
        self.mouse = None

    def run(self, *args):
        if args[0] == "xdotool":
            args = (self.request["xdotool"], *args[1:])
        try:
            return subprocess.check_output(
                args, text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdapterError(f"{args[0]} failed.") from exc

    def showing(self, node):
        return node.get_state_set().contains(self.A.StateType.SHOWING)

    def editable(self, node):
        return node.get_state_set().contains(self.A.StateType.EDITABLE)

    def walk(self, root):
        stack = [(root, 0)]
        count = 0
        while stack:
            node, depth = stack.pop()
            if node is None:
                continue
            count += 1
            if count > 4000 or depth > 30:
                raise AdapterError("WeChat accessibility tree exceeds supported limits.")
            try:
                yield node
                children = node.get_child_count()
                stack.extend(
                    (node.get_child_at_index(i), depth + 1) for i in reversed(range(children))
                )
            except self.GLib.Error:
                continue

    def nodes(self):
        self.app.clear_cache()
        return [n for n in self.walk(self.app) if self.showing(n)]

    def wait(self, predicate):
        deadline = time.monotonic() + self.timeout
        while True:
            value = predicate()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise AdapterError("Timed out waiting for the WeChat UI to update.")
            time.sleep(0.15)

    def start(self):
        desktop = self.A.get_desktop(0)
        apps = [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]
        apps = [a for a in apps if a and a.get_name().lower() in ("wechat", "weixin")]
        matches = []
        for app in apps:
            windows = self.run(
                "xdotool", "search", "--onlyvisible", "--pid", str(app.get_process_id())
            ).split()
            wanted = self.request.get("window_id")
            if wanted:
                windows = [w for w in windows if w == str(wanted)]
            # Main application should have exactly one visible top-level frame.
            frames = [app.get_child_at_index(i) for i in range(app.get_child_count())]
            frames = [f for f in frames if f and self.showing(f) and f.get_role_name() == "frame"]
            if len(windows) == 1 and len(frames) == 1:
                matches.append((app, windows[0], frames[0]))
        if len(matches) != 1:
            raise AdapterError(
                "No unique WeChat AT-SPI main window found. Sign in and start with QT_ACCESSIBILITY=1 "
                "QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 /usr/bin/wechat, or use wecli launch. Use --window-id to select a window."
            )
        self.app, self.window, frame = matches[0]
        if not account_matches(self.app.get_process_id(), self.request["db_dir"]):
            raise AdapterError(
                "The running account does not match the --config database directory, or process files cannot be read."
            )
        display = self.G.Display.get_default()
        if not display or display.get_n_monitors() != 1:
            raise AdapterError("Automatic sending requires a single X11 display.")
        monitor = display.get_monitor(0)
        r = monitor.get_geometry()
        self.monitor = r.x, r.y, r.width, r.height
        self.scale = monitor.get_scale_factor()
        self.screen = tuple(map(int, self.run("xdotool", "getdisplaygeometry").split()))
        r = frame.get_extents(self.A.CoordType.SCREEN)
        geometry = dict(
            line.split("=", 1)
            for line in self.run(
                "xdotool", "getwindowgeometry", "--shell", self.window
            ).splitlines()
            if "=" in line
        )
        if (
            abs(r.width * self.scale - int(geometry["WIDTH"])) > 4 * self.scale
            or abs(r.height * self.scale - int(geometry["HEIGHT"])) > 40 * self.scale
        ):
            raise AdapterError(
                "WeChat and desktop scaling disagree; cannot safely convert control coordinates."
            )
        # Validate display mapping before changing the desktop.
        physical_point((0, 0, 1, 1), self.monitor, self.scale, self.screen)
        self.origin = self.run("xdotool", "getactivewindow")
        self.mouse = dict(
            line.split("=", 1)
            for line in self.run("xdotool", "getmouselocation", "--shell").splitlines()
            if "=" in line
        )
        self.run("xdotool", "windowactivate", "--sync", self.window)
        self.focus()

    def focus(self):
        if self.run("xdotool", "getactivewindow") != self.window:
            raise AdapterError("WeChat window focus changed. Operation stopped.")

    def click(self, node, before_click=None):
        self.focus()
        if not self.showing(node):
            raise AdapterError("Target control is not visible.")
        r = node.get_extents(self.A.CoordType.SCREEN)
        x, y = physical_point((r.x, r.y, r.width, r.height), self.monitor, self.scale, self.screen)
        self.run("xdotool", "mousemove", "--sync", str(x), str(y))
        self.focus()
        if before_click:
            before_click()
        self.run("xdotool", "click", "1")

    def current_input(self):
        nodes = self.nodes()
        inputs = [n for n in nodes if self.editable(n) and n.get_name() in self.names]
        titles = [n for n in nodes if n.get_role_name() == "label" and n.get_name() in self.names]
        if len(inputs) == 1 and titles:
            return inputs[0]
        return None

    def select_chat(self):
        if self.current_input():
            return
        chats = [
            n
            for n in self.nodes()
            if n.get_role_name() == "list" and n.get_name() in ("Chats", "聊天")
        ]
        candidates = []
        for chat in chats:
            for i in range(chat.get_child_count()):
                n = chat.get_child_at_index(i)
                if (
                    n
                    and self.showing(n)
                    and any(
                        n.get_name() == name or n.get_name().startswith(name + " ")
                        for name in self.names
                    )
                ):
                    candidates.append(n)
        if len(candidates) == 1:
            self.click(candidates[0])
            self.wait(self.current_input)
            return
        self.search_chat()

    def search_chat(self):
        # Search only exact local contact results; never open Internet suggestions.
        searches = [
            n for n in self.nodes() if self.editable(n) and n.get_name() in ("Search", "搜索")
        ]
        if len(searches) != 1:
            raise AdapterError("Cannot locate a unique chat item or search box.")
        search = searches[0]
        if not search.grab_focus() or not search.set_text_contents(self.names[0]):
            raise AdapterError("Cannot operate the WeChat search box.")
        self.focus()
        # Qt search requires a real edit event after EditableText assignment.
        self.run("xdotool", "key", "--clearmodifiers", "End", "space", "BackSpace")

        def result():
            nodes = self.nodes()
            hits = [
                n for n in nodes if n.get_role_name() == "list item" and n.get_name() in self.names
            ]
            if len(hits) > 1:
                raise AdapterError("WeChat search returned ambiguous names. Operation stopped.")
            return hits[0] if hits else None

        hit = self.wait(result)
        self.click(hit)
        self.wait(self.current_input)

    def matching_messages(self):
        count = 0
        for node in self.nodes():
            if node.get_role_name() == "list" and node.get_name() in (
                "Messages",
                "消息",
            ):
                for i in range(node.get_child_count()):
                    child = node.get_child_at_index(i)
                    if (
                        child
                        and child.get_role_name() == "list item"
                        and child.get_name().rstrip() == self.message.rstrip()
                    ):
                        count += 1
        return count

    def submit(self):
        self.start()
        self.select_chat()
        field = self.current_input()
        if field is None or field.get_character_count() != 0:
            raise AdapterError("The target chat has a draft. Resolve it in WeChat before retrying.")
        before = self.matching_messages()
        if not field.set_text_contents(self.message) or field.get_text(0, -1) != self.message:
            raise AdapterError(
                "Input text did not match on readback. Operation stopped; check the WeChat draft."
            )

        def ready():
            buttons = [
                n
                for n in self.nodes()
                if n.get_role_name() == "push button"
                and n.get_name() in ("Send(S)", "Send", "发送(S)", "发送")
                and n.get_state_set().contains(self.A.StateType.ENABLED)
            ]
            if len(buttons) > 1:
                raise AdapterError("Cannot identify a unique Send button.")
            return buttons[0] if buttons else None

        button = self.wait(ready)

        def verify_and_mark():
            field = self.current_input()
            if field is None or field.get_text(0, -1) != self.message:
                raise AdapterError("Recipient or draft changed before sending. Operation stopped.")
            self.focus()
            # Any error starting the click is uncertain. Never click a second time.
            self.attempted = True

        self.click(button, verify_and_mark)

        def confirmed():
            field = self.current_input()
            return (
                field is not None
                and field.get_character_count() == 0
                and self.matching_messages() > before
            )

        self.wait(confirmed)
        return dict(status="submitted", ui_confirmed=True, scale=self.scale)

    def restore(self):
        # Restoration never changes the submission result or causes another send.
        try:
            if self.origin and self.run("xdotool", "getactivewindow") == self.window:
                if self.mouse:
                    self.run("xdotool", "mousemove", self.mouse["X"], self.mouse["Y"])
                self.run("xdotool", "windowactivate", "--sync", self.origin)
        except AdapterError:
            pass


def inspect_environment(request):
    import gi

    gi.require_version("Atspi", "2.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Atspi, Gdk

    Atspi.set_timeout(1000, 1000)
    info = dict(
        status="not_ready",
        python=sys.executable,
        prefix=sys.prefix,
        gi_path=gi.__file__,
        xdotool=request["xdotool"],
        session=os.environ.get("XDG_SESSION_TYPE"),
        display=os.environ.get("DISPLAY"),
        session_bus=bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")),
        wechat_apps=[],
        monitors=[],
    )
    if not info["display"] or not info["session_bus"] or info["session"] == "wayland":
        info["error"] = "A local X11 desktop session and session D-Bus are required."
        return info
    display = Gdk.Display.get_default()
    if not display:
        info["error"] = "Cannot connect to the display."
        return info
    for i in range(display.get_n_monitors()):
        monitor = display.get_monitor(i)
        rect = monitor.get_geometry()
        info["monitors"].append(
            dict(
                x=rect.x,
                y=rect.y,
                width=rect.width,
                height=rect.height,
                scale=monitor.get_scale_factor(),
            )
        )
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app and app.get_name().lower() in ("wechat", "weixin"):
            info["wechat_apps"].append(dict(name=app.get_name(), pid=app.get_process_id()))
    # These are loaded library paths, not claims derived from package metadata.
    libraries = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        path = line.split()[-1]
        if path.startswith("/") and any(
            name in Path(path).name
            for name in (
                "libatspi",
                "libgdk-3",
                "libgtk-3",
                "libgirepository",
                "libgobject",
                "libglib-2",
                "libgio-2",
                "libcairo",
            )
        ):
            libraries.add(path)
    info["native_libraries"] = sorted(libraries)
    info["dependencies_in_prefix"] = (
        Path(sys.prefix) in Path(gi.__file__).parents
        and bool(libraries)
        and all(Path(sys.prefix) in Path(p).parents for p in libraries)
        and Path(sys.prefix) in Path(request["xdotool"]).parents
    )
    if len(info["wechat_apps"]) != 1:
        info["error"] = "No unique WeChat AT-SPI main process found. Run wecli launch and sign in."
    elif len(info["monitors"]) != 1:
        info["error"] = "Sending requires a single display."
    else:
        pid = info["wechat_apps"][0]["pid"]
        roots = set()
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                path = os.readlink(fd)
                if "/db_storage/" in path:
                    roots.add(path.split("/db_storage/")[0] + "/db_storage")
            except OSError:
                continue
        info["wechat_apps"][0]["database_roots"] = sorted(roots)
        if roots:
            info["status"] = "ready"
        else:
            info["error"] = (
                "WeChat is not signed in, or the open account database could not be identified."
            )
    return info


def main():
    adapter = None
    lock_fd = None
    try:
        request = json.load(sys.stdin)
        if request.get("operation") == "inspect":
            print(json.dumps(inspect_environment(request), ensure_ascii=False))
            return
        lock_path = Path(tempfile.gettempdir()) / f"wecli-send-{os.getuid()}.lock"
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        info = os.fstat(lock_fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
            raise AdapterError("The send lock file is not owned by the current user.")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AdapterError(
                "Another wecli send is operating the desktop. Wait for it to finish."
            ) from exc
        adapter = Adapter(request)
        response = adapter.submit()
    except (ImportError, ValueError):
        response = dict(
            status="failed",
            error="AT-SPI dependencies are unavailable in this Python environment. Update using environment.yml, then run wecli doctor.",
        )
    except Exception as exc:
        attempted = adapter is not None and adapter.attempted
        response = dict(
            status="unknown" if attempted else "failed",
            ui_confirmed=False,
            error=str(exc)
            if isinstance(exc, (AdapterError, OSError))
            else "AT-SPI control operation failed. Check the WeChat window.",
        )
    finally:
        if adapter:
            adapter.restore()
        if lock_fd is not None:
            os.close(lock_fd)
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
