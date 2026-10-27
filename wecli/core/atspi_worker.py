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
        raise AdapterError("显示坐标与缩放不一致；当前支持单屏整数缩放 X11。")
    x, y, w, h = rect
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > mw or y + h > mh:
        raise AdapterError("目标控件不完全在屏幕内，请将微信窗口移到屏幕内再执行。")
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
            raise AdapterError(f"{args[0]} 操作失败。") from exc

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
                raise AdapterError("微信控件树超出支持范围。")
            try:
                yield node
                children = node.get_child_count()
                stack.extend(
                    (node.get_child_at_index(i), depth + 1)
                    for i in reversed(range(children))
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
                raise AdapterError("等待微信界面更新超时。")
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
            frames = [
                f
                for f in frames
                if f and self.showing(f) and f.get_role_name() == "frame"
            ]
            if len(windows) == 1 and len(frames) == 1:
                matches.append((app, windows[0], frames[0]))
        if len(matches) != 1:
            raise AdapterError(
                "未找到唯一微信 AT-SPI 主窗口。请登录，并用 QT_ACCESSIBILITY=1 "
                "QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 /usr/bin/wechat 启动，或使用 wecli launch；多窗口可指定 --window-id。"
            )
        self.app, self.window, frame = matches[0]
        if not account_matches(self.app.get_process_id(), self.request["db_dir"]):
            raise AdapterError(
                "运行中微信账号与 --config 的数据库目录不匹配，或无法读取进程文件列表。"
            )
        display = self.G.Display.get_default()
        if not display or display.get_n_monitors() != 1:
            raise AdapterError("当前自动发送只支持单显示器 X11，会拒绝多屏布局。")
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
            raise AdapterError("微信与桌面缩放不一致，无法安全转换控件坐标。")
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
            raise AdapterError("微信窗口焦点改变，已停止操作。")

    def click(self, node, before_click=None):
        self.focus()
        if not self.showing(node):
            raise AdapterError("目标控件不可见。")
        r = node.get_extents(self.A.CoordType.SCREEN)
        x, y = physical_point(
            (r.x, r.y, r.width, r.height), self.monitor, self.scale, self.screen
        )
        self.run("xdotool", "mousemove", "--sync", str(x), str(y))
        self.focus()
        if before_click:
            before_click()
        self.run("xdotool", "click", "1")

    def current_input(self):
        nodes = self.nodes()
        inputs = [n for n in nodes if self.editable(n) and n.get_name() in self.names]
        titles = [
            n
            for n in nodes
            if n.get_role_name() == "label" and n.get_name() in self.names
        ]
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
            n
            for n in self.nodes()
            if self.editable(n) and n.get_name() in ("Search", "搜索")
        ]
        if len(searches) != 1:
            raise AdapterError("无法定位唯一聊天项或搜索框。")
        search = searches[0]
        if not search.grab_focus() or not search.set_text_contents(self.names[0]):
            raise AdapterError("无法操作微信搜索框。")
        self.focus()
        # Qt search requires a real edit event after EditableText assignment.
        self.run("xdotool", "key", "--clearmodifiers", "End", "space", "BackSpace")

        def result():
            nodes = self.nodes()
            hits = [
                n
                for n in nodes
                if n.get_role_name() == "list item" and n.get_name() in self.names
            ]
            if len(hits) > 1:
                raise AdapterError("微信搜索出现多个同名结果，已停止。")
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
            raise AdapterError("目标聊天已有草稿，已停止；请自行处理草稿后再运行。")
        before = self.matching_messages()
        if (
            not field.set_text_contents(self.message)
            or field.get_text(0, -1) != self.message
        ):
            raise AdapterError("输入框文本回读不一致，已停止；请检查微信草稿。")

        def ready():
            buttons = [
                n
                for n in self.nodes()
                if n.get_role_name() == "push button"
                and n.get_name() in ("Send(S)", "Send", "发送(S)", "发送")
                and n.get_state_set().contains(self.A.StateType.ENABLED)
            ]
            if len(buttons) > 1:
                raise AdapterError("无法确定唯一发送按钮。")
            return buttons[0] if buttons else None

        button = self.wait(ready)

        def verify_and_mark():
            field = self.current_input()
            if field is None or field.get_text(0, -1) != self.message:
                raise AdapterError("发送前收件人或草稿改变，已停止。")
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
        info["error"] = "需要本机 X11 图形会话和会话 D-Bus。"
        return info
    display = Gdk.Display.get_default()
    if not display:
        info["error"] = "无法连接图形显示。"
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
            info["wechat_apps"].append(
                dict(name=app.get_name(), pid=app.get_process_id())
            )
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
        info["error"] = "未发现唯一微信 AT-SPI 主进程，请先运行 wecli launch 并登录。"
    elif len(info["monitors"]) != 1:
        info["error"] = "当前发送只支持单显示器。"
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
            info["error"] = "微信尚未登录，或无法确认已打开的账号数据库。"
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
            raise AdapterError("发送锁文件不属于当前用户。")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AdapterError("另一个 wecli send 正在操作桌面，请等待完成。") from exc
        adapter = Adapter(request)
        response = adapter.submit()
    except (ImportError, ValueError):
        response = dict(
            status="failed",
            error="当前 Python 的 AT-SPI 依赖不可用，请按 environment.yml 更新环境，然后运行 wecli doctor。",
        )
    except Exception as exc:
        attempted = adapter is not None and adapter.attempted
        response = dict(
            status="unknown" if attempted else "failed",
            ui_confirmed=False,
            error=str(exc)
            if isinstance(exc, (AdapterError, OSError))
            else "AT-SPI 控件操作异常，请检查微信窗口。",
        )
    finally:
        if adapter:
            adapter.restore()
        if lock_fd is not None:
            os.close(lock_fd)
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
