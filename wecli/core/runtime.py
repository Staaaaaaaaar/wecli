"""Runtime-owned desktop tools and a clean environment for the official app."""

import os
import shutil
import sys
from pathlib import Path


class RuntimeErrorDetail(RuntimeError):
    pass


def in_conda():
    return (Path(sys.prefix) / "conda-meta").is_dir()


def desktop_tool(name):
    local = Path(sys.prefix) / "bin" / name
    if local.is_file() and os.access(local, os.X_OK):
        if in_conda() and Path(sys.prefix).resolve() not in local.resolve().parents:
            raise RuntimeErrorDetail(
                f"{name} is outside the active Conda environment. Repair it using environment.yml."
            )
        return str(local)
    if in_conda():
        raise RuntimeErrorDetail(
            f"The active Conda environment is missing {name}. Update it using environment.yml."
        )
    found = shutil.which(name)
    if not found:
        raise RuntimeErrorDetail(
            f"Missing {name}. Create the runtime environment using environment.yml."
        )
    return found


def worker_environment():
    env = dict(os.environ)
    if in_conda():
        # Avoid typelibs / dynamic loader overrides inherited from other runtimes.
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        env["GI_TYPELIB_PATH"] = str(Path(sys.prefix) / "lib/girepository-1.0")
        env["GIO_EXTRA_MODULES"] = str(Path(sys.prefix) / "lib/gio/modules")
        env["GSETTINGS_SCHEMA_DIR"] = str(Path(sys.prefix) / "share/glib-2.0/schemas")
    return env


def wechat_processes(proc_root=Path("/proc")):
    result = []
    for path in proc_root.iterdir():
        if not path.name.isdecimal():
            continue
        try:
            if path.stat().st_uid == os.getuid() and (
                path / "comm"
            ).read_text().strip().lower() in ("wechat", "weixin"):
                result.append(int(path.name))
        except OSError:
            continue
    return sorted(result)


def clean_wechat_env(source=None):
    """Preserve desktop/login/network variables, remove injected runtime paths."""
    env = dict(os.environ if source is None else source)
    for key in list(env):
        if key.startswith(("CONDA_", "_CE_", "PYTHON", "GI_")) or key in (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "QML_IMPORT_PATH",
            "GTK_PATH",
            "GTK_EXE_PREFIX",
            "GTK_DATA_PREFIX",
            "GTK_MODULES",
            "GDK_PIXBUF_MODULE_FILE",
            "GDK_PIXBUF_MODULEDIR",
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
            "LIBRARY_PATH",
            "GIO_EXTRA_MODULES",
            "GIO_MODULE_DIR",
            "GSETTINGS_SCHEMA_DIR",
            "CMAKE_PREFIX_PATH",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "FONTCONFIG_FILE",
            "FONTCONFIG_PATH",
        ):
            env.pop(key, None)
    # Do not pass Conda/venv executables to any official-client subprocess.
    prefixes = [sys.prefix] if in_conda() or sys.prefix != sys.base_prefix else []
    if in_conda() and Path(sys.prefix).parent.name == "envs":
        prefixes.append(str(Path(sys.prefix).parent.parent))
    prefixes += [
        value
        for key, value in (os.environ if source is None else source).items()
        if key.startswith("CONDA_PREFIX") or key == "VIRTUAL_ENV"
    ]
    paths = env.get("PATH", "").split(os.pathsep)

    def external(path):
        if not path:
            return False
        resolved = Path(path).resolve()
        return not any(
            resolved == Path(p).resolve() or Path(p).resolve() in resolved.parents for p in prefixes
        )

    if "XDG_DATA_DIRS" in env:
        data_dirs = [p for p in env["XDG_DATA_DIRS"].split(os.pathsep) if external(p)]
        if data_dirs:
            env["XDG_DATA_DIRS"] = os.pathsep.join(data_dirs)
        else:
            env.pop("XDG_DATA_DIRS")
    env["PATH"] = os.pathsep.join(p for p in paths if external(p))
    if not env["PATH"]:
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    env.pop("VIRTUAL_ENV", None)
    env.update(QT_ACCESSIBILITY="1", QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1")
    return env
