"""
Load test for Smart Medical ID (Locust).

Prepare users once:   python manage.py seed_demo --load-users 100
Run (headless):       locust -f loadtest/locustfile.py --host http://127.0.0.1:8100 --headless -u 100 -r 10 -t 90s

Simulates the real mix: patients polling notifications, opening the dashboard, browsing the
doctors directory, checking free slots and booking/cancelling; staff working the requests
queue, calendar and patient records. The AI guide is excluded (LLM time would dominate).
"""
import datetime as dt
import random

from locust import HttpUser, between, task

PATIENT_COUNT = 100
PASSWORD_PATIENT = "LoadTest#2026"
STAFF = [("dr.samer", "Strong@123"), ("nurse.lina", "Strong@123")]


class Base(HttpUser):
    abstract = True
    wait_time = between(1, 4)

    def login(self, username, password):
        r = self.client.post("/api/token/", json={"username": username, "password": password}, name="POST /api/token/")
        r.raise_for_status()
        self.client.headers["Authorization"] = "Bearer " + r.json()["access"]


class Patient(Base):
    weight = 8

    def on_start(self):
        self.login(f"loadpatient{random.randint(1, PATIENT_COUNT)}", PASSWORD_PATIENT)
        docs = self.client.get("/api/doctors/?bookable=1&page_size=50", name="/api/doctors/?bookable").json()["results"]
        self.doctors = [d["id"] for d in docs] or [1]

    @task(6)
    def poll_notifications(self):
        self.client.get("/api/notifications/unread-count/")

    @task(4)
    def dashboard(self):
        self.client.get("/api/dashboard/", name="/api/dashboard/ [patient]")

    @task(3)
    def browse_directory(self):
        spec = random.choice(["", "CARDIOLOGY", "INTERNAL", "DERMATOLOGY", "ENT"])
        self.client.get(f"/api/doctors/?specialty={spec}&page_size=12", name="/api/doctors/?specialty")

    @task(3)
    def slots(self):
        self.client.get(f"/api/doctors/{random.choice(self.doctors)}/slots/?days=14", name="/api/doctors/[id]/slots/")

    @task(2)
    def my_record(self):
        self.client.get("/api/me/")

    @task(2)
    def my_appointments(self):
        self.client.get("/api/appointments/?when=upcoming", name="/api/appointments/ [patient]")

    @task(1)
    def book_and_maybe_cancel(self):
        doc = random.choice(self.doctors)
        days = self.client.get(f"/api/doctors/{doc}/slots/?days=14", name="/api/doctors/[id]/slots/").json()["days"]
        free = [s["start"] for d in days for s in d["slots"] if s["available"]]
        if not free:
            return
        with self.client.post("/api/appointments/book/", json={"doctor": doc, "start_at": random.choice(free)},
                              name="POST /api/appointments/book/", catch_response=True) as r:
            if r.status_code == 400 and ("slot_taken" in r.text or "too_many" in r.text):
                r.success()  # expected under contention: another user took the slot first
                return
            if r.status_code != 201:
                r.failure(f"{r.status_code} {r.text[:120]}")
                return
        if random.random() < 0.7:  # free most slots again so the test can keep booking
            self.client.post(f"/api/appointments/{r.json()['id']}/cancel/", name="POST /api/appointments/[id]/cancel/")

    @task(1)
    def static_page(self):
        self.client.get("/patient/dashboard.html", name="static page", headers={"Authorization": ""})


class Staff(Base):
    weight = 2

    def on_start(self):
        self.login(*random.choice(STAFF))
        self.patient_ids = [p["id"] for p in self.client.get("/api/patients/?page_size=50", name="/api/patients/?search").json()["results"]]

    @task(4)
    def poll(self):
        self.client.get("/api/notifications/unread-count/")

    @task(3)
    def dashboard(self):
        self.client.get("/api/dashboard/", name="/api/dashboard/ [staff]")

    @task(3)
    def requests(self):
        r = self.client.get("/api/appointments/?status=PENDING&when=upcoming", name="/api/appointments/?PENDING")
        pending = r.json().get("results", [])
        if pending and random.random() < 0.5:
            a = random.choice(pending)
            action = "approve" if random.random() < 0.8 else "reject"
            with self.client.post(f"/api/appointments/{a['id']}/{action}/", json={}, name=f"POST /api/appointments/[id]/{action}/",
                                  catch_response=True) as resp:
                if resp.status_code == 400:
                    resp.success()  # already handled by the other staff user / cancelled by patient

    @task(2)
    def calendar(self):
        start = dt.date.today()
        self.client.get(f"/api/appointments/calendar/?start={start}T00:00:00Z&end={start + dt.timedelta(days=7)}T00:00:00Z",
                        name="/api/appointments/calendar/")

    @task(2)
    def patients(self):
        self.client.get(f"/api/patients/?search={random.choice(['', 'مريض', 'Nour', 'SMI'])}", name="/api/patients/?search")

    @task(1)
    def record(self):
        self.client.get(f"/api/patients/{random.choice(self.patient_ids)}/record/", name="/api/patients/[id]/record/")
