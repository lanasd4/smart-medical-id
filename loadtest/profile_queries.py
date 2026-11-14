"""
Counts SQL queries and server time per endpoint (catches N+1 problems).

    cd backend
    .venv\\Scripts\\python.exe ..\\loadtest\\profile_queries.py
"""
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
os.environ["AI_ENABLED"] = "0"
os.environ["PUSH_ENABLED"] = "0"

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

settings.ALLOWED_HOSTS = ["*"]
from core_app.models import DoctorProfile, Patient  # noqa: E402

doc = DoctorProfile.objects.filter(user__username="dr.samer").first()
pat = Patient.objects.filter(user__username="patient.nour").first()

CASES = {
    "patient.nour": ["/api/dashboard/", "/api/me/", "/api/appointments/?when=upcoming", "/api/notifications/unread-count/",
                     "/api/doctors/?page_size=12", f"/api/doctors/{doc.id}/slots/?days=14", "/api/whoami/"],
    "dr.samer": ["/api/dashboard/", "/api/appointments/?status=PENDING&when=upcoming", "/api/appointments/calendar/",
                 "/api/patients/?page_size=20", f"/api/patients/{pat.id}/record/", "/api/notifications/?page_size=8"],
    "admin": ["/api/dashboard/", "/api/users/?page_size=20", "/api/doctors/?all=1&page_size=20", "/api/admin/audit-events/?page_size=50"],
}

print(f"{'user':<14}{'endpoint':<52}{'status':>6}{'queries':>9}{'ms':>9}")
worst = []
for username, urls in CASES.items():
    client = APIClient()
    client.force_authenticate(User.objects.get(username=username))
    for url in urls:
        client.get(url)  # warm-up
        with CaptureQueriesContext(connection) as ctx:
            t0 = time.perf_counter()
            r = client.get(url)
            ms = (time.perf_counter() - t0) * 1000
        print(f"{username:<14}{url[:50]:<52}{r.status_code:>6}{len(ctx.captured_queries):>9}{ms:>9.1f}")
        worst.append((len(ctx.captured_queries), url))
print("\nmost queries:", sorted(worst, reverse=True)[:3])
