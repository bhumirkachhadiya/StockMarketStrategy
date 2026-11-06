"""
Universal Application & Gunicorn Compatibility Runner
Intercepts 'gunicorn' CLI calls from cloud hosting environments (Render / Railway / Heroku)
and cleanly boots the native SocketIO multithreaded server on the specified port.
"""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("ServerRunner")

def run_gunicorn_shim():
    # Ensure current working directory and script directory are in sys.path
    cwd = os.getcwd()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for path in (cwd, script_dir):
        if path not in sys.path:
            sys.path.insert(0, path)

    port = int(os.environ.get("PORT", 8080))

    # Parse port from --bind / -b argument if provided
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg in ("--bind", "-b") and i + 1 < len(args):
            bind_val = args[i + 1]
            if ":" in bind_val:
                try:
                    port = int(bind_val.split(":")[-1])
                except ValueError:
                    pass
        elif arg.startswith("--bind="):
            bind_val = arg.split("=")[1]
            if ":" in bind_val:
                try:
                    port = int(bind_val.split(":")[-1])
                except ValueError:
                    pass

    logger.info(f"Cloud boot sequence initiated on port {port} (argv: {sys.argv})")

    # Import and run app via socketio
    from app import app, socketio
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    run_gunicorn_shim()
