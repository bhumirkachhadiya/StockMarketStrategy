"""
Gunicorn Eventlet Worker Compatibility Shim
Redirects deprecated 'eventlet' worker requests to multithreaded worker
matching Flask-SocketIO async_mode='threading'.
"""
import sys

try:
    from gunicorn.workers.gthread import ThreadWorker
    class EventletShimWorker(ThreadWorker):
        pass
except ImportError:
    class EventletShimWorker:
        pass
