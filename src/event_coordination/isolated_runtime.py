"""Private Linux namespace setup for the supervised runner; not an authorization API.

Executed only by the parent backend after unshare. No shell or configurable argv.
"""

import ctypes
import json
import os
from pathlib import Path
import resource
import stat
import sys

VIRTUAL_ROOT = "/home/maxg/event-coordination"
NAMESPACES = ("user", "mnt", "net", "pid", "ipc")
FLAGS = ("--capture=sys", "--log-file=/scratch/pytest.log", "--junitxml=/proc/self/fd/3",
         "-q", "-p", "no:cacheprovider")
TASKS = {
    "automation-tests": (".venv/bin/python", "-m", "pytest", "tests/test_automation.py", *FLAGS),
    "stage6-tests": (".venv/bin/python", "-m", "pytest", "tests/test_stage6.py", *FLAGS),
    "regression-tests": (".venv/bin/python", "-m", "pytest", *FLAGS),
}


def setup(root, source, runtime, task, parent_namespaces, result_fd):
    """Install private mounts, drop privilege, then replace PID 1 with pytest."""
    if sys.platform != "linux" or os.uname().machine != "x86_64" or task not in TASKS:
        raise ValueError("UNSUPPORTED_RUNTIME")
    # A direct invocation without every required private namespace stops before mounting.
    parent_namespaces = json.loads(parent_namespaces)
    for name in NAMESPACES:
        if os.readlink(f"/proc/self/ns/{name}") == parent_namespaces[name]:
            raise ValueError("NAMESPACE_REQUIRED")
    libc = ctypes.CDLL(None, use_errno=True)

    def mount(src, dest, flags=0, kind=None, data=None):
        result = libc.mount(src.encode() if src else None, str(dest).encode(),
                            kind.encode() if kind else None, flags, data.encode() if data else None)
        if result:
            raise OSError(ctypes.get_errno(), "ISOLATION_MOUNT_FAILED")

    class Attr(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("set", "clear", "propagation", "userns")]

    def bind(src, relative):
        dest = Path(root) / relative.lstrip("/")
        dest.mkdir(parents=True, exist_ok=True)
        mount(str(src), dest, 4096 | 16384)  # recursive bind preserves locked WSL submounts
        attr = Attr(1 | 2 | 4, 0, 0, 0)  # read-only, nosuid, nodev, recursively
        if libc.syscall(442, -100, str(dest).encode(), 0x8000, ctypes.byref(attr), ctypes.sizeof(attr)):
            raise OSError(ctypes.get_errno(), "RECURSIVE_READONLY_FAILED")

    mount(None, "/", (1 << 18) | (1 << 14))
    mount("tmpfs", root, 2 | 4, "tmpfs", "size=32m")
    for name in ("usr", "lib", "lib64", "bin"):
        if Path("/" + name).exists():
            bind("/" + name, name)
    bind(source, VIRTUAL_ROOT)
    bind(runtime, VIRTUAL_ROOT + "/.venv")
    for name in ("scratch", "tmp", "proc"):
        (Path(root) / name).mkdir()
    for name in ("scratch", "tmp"):
        mount("tmpfs", Path(root) / name, 2 | 4 | 8, "tmpfs", "size=64m")
    mount("proc", Path(root) / "proc", 1 | 2 | 4 | 8, "proc")
    mount(None, root, 32 | 1 | 2 | 4, "tmpfs", "size=32m")
    os.chroot(root)
    os.chdir(VIRTUAL_ROOT)
    if libc.prctl(38, 1, 0, 0, 0):
        raise OSError("NO_NEW_PRIVILEGES_FAILED")
    for cap in range(41):
        if libc.prctl(24, cap, 0, 0, 0):
            raise OSError("CAPABILITY_BOUNDING_DROP_FAILED")

    class Header(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

    class Data(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint32) for n in ("effective", "permitted", "inheritable")]

    header, data = Header(0x20080522, 0), (Data * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)):
        raise OSError("CAPABILITY_DROP_FAILED")
    if libc.capget(ctypes.byref(header), ctypes.byref(data)) or any(d.effective or d.permitted for d in data):
        raise OSError("CAPABILITY_DROP_FAILED")
    for identifier, limit in ((resource.RLIMIT_CPU, 300), (resource.RLIMIT_AS, 1024**3),
                              (resource.RLIMIT_FSIZE, 2 * 1024**2), (resource.RLIMIT_NOFILE, 128),
                              (resource.RLIMIT_NPROC, 64), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(identifier, (limit, limit))
    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "TMPDIR": "/tmp", "LANG": "C.UTF-8"}
    argv = [VIRTUAL_ROOT + "/" + TASKS[task][0], *TASKS[task][1:]]
    # The only extra inherited descriptor is an explicitly writable temporary
    # result artifact, not a directory or host evidence. Pin its child-side name.
    result_fd = int(result_fd)
    if result_fd < 3 or not stat.S_ISREG(os.fstat(result_fd).st_mode):
        raise ValueError("INVALID_RESULT_DESCRIPTOR")
    os.dup2(result_fd, 3, inheritable=True)
    if result_fd != 3:
        os.close(result_fd)
    os.execve(argv[0], argv, env)


if __name__ == "__main__":
    try:
        setup(*sys.argv[1:])
    except Exception:
        # Setup diagnostics never expose host paths, configuration or credentials.
        print(json.dumps({"error_code": "ISOLATION_SETUP_FAILED"}), file=sys.stderr)
        raise SystemExit(125)
