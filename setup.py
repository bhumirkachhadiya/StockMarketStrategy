from setuptools import setup

setup(
    name="stock-strategy-runner",
    version="1.0.0",
    py_modules=[],
    entry_points={
        "gunicorn.workers": [
            "eventlet = gunicorn.workers.gthread:ThreadWorker",
            "sync = gunicorn.workers.sync:SyncWorker",
            "gthread = gunicorn.workers.gthread:ThreadWorker",
        ],
    },
)
