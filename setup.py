from setuptools import setup

setup(
    name="stock-strategy-runner",
    version="1.0.0",
    py_modules=["worker_shim"],
    entry_points={
        "gunicorn.workers": [
            "eventlet = worker_shim:EventletShimWorker",
        ],
    },
)
