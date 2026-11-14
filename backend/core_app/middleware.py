"""Keeps the current request available to model signals (used by the audit log)."""
import threading

_thread_local = threading.local()


def get_current_request():
    return getattr(_thread_local, "request", None)


def get_current_user():
    request = get_current_request()
    user = getattr(request, "user", None) if request is not None else None
    return user if user is not None and getattr(user, "is_authenticated", False) else None


def get_current_ip():
    request = get_current_request()
    if request is None:
        return None
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR"))


def get_current_session_key():
    return None


class ThreadLocalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_local.request = request
        try:
            return self.get_response(request)
        finally:
            _thread_local.request = None
