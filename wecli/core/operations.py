"""Durable send attempts and a lock covering baseline, UI and receipt."""

import fcntl
import os
import stat
from contextlib import contextmanager

from .config import atomic_write_json
from .stream import account_id


@contextmanager
def send_lock():
    path = f"/tmp/wecli-operation-{os.getuid()}.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
            raise ValueError("Invalid send operation lock owner or file type")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def operation_path(app, operation_id):
    import uuid

    if str(uuid.UUID(operation_id)) != operation_id:
        raise ValueError("Invalid operation ID")
    return os.path.join(
        os.path.dirname(app.keys_file), "operations", account_id(app), operation_id + ".json"
    )


def save_operation(app, result):
    atomic_write_json(operation_path(app, result["operation_id"]), result)
