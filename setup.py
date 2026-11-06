import os
import sys
from setuptools import setup

# Install the universal interceptor script directly into the virtualenv bin directory
try:
    bin_dir = os.path.dirname(sys.executable)
    wrapper_code = '''#!/usr/bin/env python3
import sys
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg in ("--bind", "-b") and i + 1 < len(args):
            val = args[i + 1]
            if ":" in val:
                try:
                    port = int(val.split(":")[-1])
                except ValueError:
                    pass
        elif arg.startswith("--bind="):
            val = arg.split("=")[1]
            if ":" in val:
                try:
                    port = int(val.split(":")[-1])
                except ValueError:
                    pass

    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    print(f"[gunicorn-interceptor] Starting native SocketIO server on port {port}...")
    from app import app, socketio
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
'''
    linux_gunicorn = os.path.join(bin_dir, "gunicorn")
    with open(linux_gunicorn, "w", encoding="utf-8", newline="\n") as f:
        f.write(wrapper_code)
    try:
        os.chmod(linux_gunicorn, 0o755)
    except Exception:
        pass
    print(f"[setup.py] Successfully installed universal interceptor to {linux_gunicorn}")
except Exception as e:
    print(f"[setup.py] Note: {e}")

setup(
    name="stock-strategy-runner",
    version="1.0.0",
    py_modules=["worker_shim"],
    entry_points={
        "console_scripts": [
            "gunicorn = worker_shim:run_gunicorn_shim",
        ],
    },
)
