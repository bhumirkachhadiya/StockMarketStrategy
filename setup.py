from setuptools import setup

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
