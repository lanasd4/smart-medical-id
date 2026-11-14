"""In-app notifications and Web Push delivery."""
import base64
import json
import logging
import threading
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import Notification, PushSubscription

log = logging.getLogger(__name__)

_vapid_lock = threading.Lock()
_vapid_cache = {}


def _vapid_paths():
    base = Path(getattr(settings, "VAPID_DIR", settings.BASE_DIR))
    return base / "vapid_private.pem"


def vapid_keys():
    """Load (or create on first use) the VAPID key pair. Returns (private_pem_path, public_key_b64url)."""
    with _vapid_lock:
        if _vapid_cache:
            return _vapid_cache["private"], _vapid_cache["public"]
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid

        pem = _vapid_paths()
        if pem.exists():
            v = Vapid.from_file(str(pem))
        else:
            v = Vapid()
            v.generate_keys()
            v.save_key(str(pem))
        raw = v.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        public = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        _vapid_cache.update(private=str(pem), public=public)
        return _vapid_cache["private"], _vapid_cache["public"]


def _send_push(subscriptions, payload):
    try:
        from pywebpush import WebPushException, webpush
        private, _ = vapid_keys()
    except Exception as exc:  # pragma: no cover - library/key problems must never break the app
        log.warning("web push unavailable: %s", exc)
        return
    claims = {"sub": getattr(settings, "VAPID_SUBJECT", "mailto:admin@smart-medical-id.app")}
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=private,
                vapid_claims=dict(claims),
                ttl=3600,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                PushSubscription.objects.filter(endpoint=sub["endpoint"]).delete()
            else:
                log.warning("push failed (%s): %s", status, exc)
        except Exception as exc:  # pragma: no cover
            log.warning("push failed: %s", exc)


def notify(users, title, body="", kind="SYSTEM", link=""):
    """Create a notification for each user (iterable of User or a single User) and push it."""
    if users is None:
        return []
    if not isinstance(users, (list, tuple, set)) and not hasattr(users, "__iter__"):
        users = [users]
    users = [u for u in users if u is not None]
    if not users:
        return []
    created = Notification.objects.bulk_create(
        [Notification(user=u, title=title[:150], body=body[:500], kind=kind, link=link) for u in users]
    )
    if getattr(settings, "PUSH_ENABLED", True):
        subs = list(PushSubscription.objects.filter(user__in=users).values("endpoint", "p256dh", "auth"))
        if subs:
            payload = {"title": title, "body": body, "url": link or "/", "kind": kind}
            transaction.on_commit(
                lambda: threading.Thread(target=_send_push, args=(subs, payload), daemon=True).start()
            )
    return created
