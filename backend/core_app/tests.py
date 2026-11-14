import datetime as dt
import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (
    Allergy, Appointment, Condition, DoctorAvailability, DoctorProfile, DocumentRef, Medication,
    Notification, Patient,
)

TMP_MEDIA = tempfile.mkdtemp()


@override_settings(PUSH_ENABLED=False, AI_ENABLED=False, MEDIA_ROOT=TMP_MEDIA,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   REST_FRAMEWORK={**__import__("django.conf").conf.settings.REST_FRAMEWORK,
                                   "DEFAULT_THROTTLE_RATES": {"auth": "1000/min", "ai": "1000/min", "public": "1000/min"}})
class Base(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.groups = {n: Group.objects.get_or_create(name=n)[0] for n in ("Admin", "Doctor", "Nurse", "Patient")}
        self.admin = self.mk("admin1", "Admin")
        self.doc_user = self.mk("doc1", "Doctor")
        self.doc2_user = self.mk("doc2", "Doctor")
        self.nurse = self.mk("nurse1", "Nurse")
        self.p_user = self.mk("pat1", "Patient")
        self.p2_user = self.mk("pat2", "Patient")
        self.patient = Patient.objects.create(user=self.p_user, name="مريض أول", date_of_birth=dt.date(1990, 1, 1))
        self.patient2 = Patient.objects.create(user=self.p2_user, name="مريض ثاني")
        self.doctor = DoctorProfile.objects.create(user=self.doc_user, full_name="سامر", specialty="CARDIOLOGY",
                                                   city="دمشق", is_verified=True, slot_minutes=30)
        self.doctor.nurses.add(self.nurse)
        for wd in range(7):
            DoctorAvailability.objects.create(doctor=self.doctor, weekday=wd,
                                              start_time=dt.time(9, 0), end_time=dt.time(12, 0))
        self.directory_only = DoctorProfile.objects.create(full_name="طبيب غير مشترك", specialty="ENT", city="حلب")

    def mk(self, username, role):
        u = User.objects.create_user(username=username, password="Str0ng!Pass#1")
        u.groups.add(self.groups[role])
        return u

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def slot(self, days_ahead=2, hour=10, minute=0):
        d = timezone.localdate() + dt.timedelta(days=days_ahead)
        return timezone.make_aware(dt.datetime.combine(d, dt.time(hour, minute)))

    def book(self, user, start, doctor=None):
        return self.as_(user).post("/api/appointments/book/", {
            "doctor": (doctor or self.doctor).id, "start_at": start.isoformat(), "reason": "فحص"}, format="json")


class PermissionsUnchangedTests(Base):
    def test_staff_see_all_patients(self):
        for u in (self.admin, self.doc_user, self.doc2_user, self.nurse):
            r = self.as_(u).get("/api/patients/?page_size=100")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data["count"], 2, u.username)

    def test_patient_sees_only_own_record(self):
        r = self.as_(self.p_user).get("/api/patients/")
        self.assertEqual([p["id"] for p in r.data["results"]], [self.patient.id])
        self.assertEqual(self.as_(self.p_user).get(f"/api/patients/{self.patient2.id}/").status_code, 404)

    def test_patient_cannot_write_medical_records(self):
        r = self.as_(self.p_user).post("/api/conditions/", {"patient": self.patient.id, "name": "سكري"}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.as_(self.p_user).post("/api/allergies/", {"patient": self.patient.id, "substance": "بنسلين"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_staff_can_write_records(self):
        r = self.as_(self.nurse).post("/api/conditions/", {"patient": self.patient.id, "name": "ضغط", "is_chronic": True}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Condition.objects.get().added_by, self.nurse)

    def test_patient_can_edit_only_contact_fields(self):
        r = self.as_(self.p_user).patch("/api/patients/me/", {"phone": "0999", "blood_type": "O+", "name": "x"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.phone, "0999")
        self.assertIsNone(self.patient.blood_type)
        self.assertEqual(self.patient.name, "مريض أول")

    def test_original_delete_rules(self):
        med = Medication.objects.create(patient=self.patient, local_name="أسبرين")
        self.assertEqual(self.as_(self.nurse).delete(f"/api/medications/{med.id}/").status_code, 403)
        self.assertEqual(self.as_(self.doc_user).delete(f"/api/medications/{med.id}/").status_code, 204)
        al = Allergy.objects.create(patient=self.patient, substance="لاتكس")
        self.assertEqual(self.as_(self.doc_user).delete(f"/api/allergies/{al.id}/").status_code, 403)
        self.assertEqual(self.as_(self.admin).delete(f"/api/allergies/{al.id}/").status_code, 204)

    def test_patient_creation_only_by_staff(self):
        r = self.as_(self.p_user).post("/api/patients/", {"name": "جديد"}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.as_(self.nurse).post("/api/patients/", {"name": "جديد", "username": "newp", "password": "Str0ng!Pass#9"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["medical_id"].startswith("SMI-"))
        self.assertTrue(User.objects.get(username="newp").groups.filter(name="Patient").exists())

    def test_users_admin_only(self):
        self.assertEqual(self.as_(self.doc_user).get("/api/users/").status_code, 403)
        self.assertEqual(self.as_(self.admin).get("/api/users/").status_code, 200)


class RegistrationTests(Base):
    payload = {"username": "newdoc", "password": "Str0ng!Pass#2", "first_name": "ليلى", "last_name": "حسن",
               "specialty": "DERMATOLOGY", "city": "حمص", "license_number": "L-123"}

    def test_patient_self_registration_is_not_allowed(self):
        self.client.force_authenticate(None)
        r = self.client.post("/api/register/", {**self.payload, "role": "patient"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username="newdoc").exists())

    def test_registered_doctor_has_no_access_until_verified(self):
        self.client.force_authenticate(None)
        r = self.client.post("/api/register/", self.payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["user"]["role"], "PendingDoctor")
        user = User.objects.get(username="newdoc")
        self.assertFalse(user.groups.exists())
        self.assertEqual(self.as_(user).get("/api/patients/").data["count"], 0)
        self.assertTrue(Notification.objects.filter(user=self.admin, kind="DOCTOR_VERIFICATION").exists())
        self.client.force_authenticate(None)
        names = [d["full_name"] for d in self.client.get("/api/doctors/?page_size=100").data["results"]]
        self.assertNotIn("ليلى حسن", names)
        prof = user.doctor_profile
        self.assertEqual(self.as_(self.admin).post(f"/api/doctors/{prof.id}/verify/", {"verified": True}, format="json").status_code, 200)
        user = User.objects.get(pk=user.pk)
        self.assertTrue(user.groups.filter(name="Doctor").exists())
        self.assertEqual(self.as_(user).get("/api/patients/").data["count"], 2)


class BookingWorkflowTests(Base):
    def test_slots_follow_working_hours(self):
        d = (timezone.localdate() + dt.timedelta(days=2)).isoformat()
        r = self.client.get(f"/api/doctors/{self.doctor.id}/slots/?from={d}&days=1")
        slots = r.data["days"][0]["slots"]
        self.assertEqual(len(slots), 6)  # 09:00-12:00 / 30 min
        self.assertTrue(all(s["available"] for s in slots))

    def test_request_then_doctor_approves(self):
        start = self.slot()
        r = self.book(self.p_user, start)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], "PENDING")
        appt_id = r.data["id"]
        # staff were notified
        self.assertTrue(Notification.objects.filter(user=self.doc_user, kind="APPOINTMENT_REQUEST").exists())
        self.assertTrue(Notification.objects.filter(user=self.nurse, kind="APPOINTMENT_REQUEST").exists())
        # the slot is now held: nobody else can see it as available or take it
        d = start.date().isoformat()
        slots = self.client.get(f"/api/doctors/{self.doctor.id}/slots/?from={d}&days=1").data["days"][0]["slots"]
        self.assertFalse(next(s for s in slots if s["start"] == timezone.localtime(start).isoformat())["available"])
        r2 = self.book(self.p2_user, start)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r2.data["code"], "slot_taken")
        # patient cannot approve their own request
        self.assertEqual(self.as_(self.p_user).post(f"/api/appointments/{appt_id}/approve/").status_code, 403)
        r = self.as_(self.doc_user).post(f"/api/appointments/{appt_id}/approve/", format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "CONFIRMED")
        self.assertTrue(Notification.objects.filter(user=self.p_user, kind="APPOINTMENT_CONFIRMED").exists())

    def test_nurse_can_reject_and_slot_is_released(self):
        start = self.slot(hour=11)
        appt_id = self.book(self.p_user, start).data["id"]
        r = self.as_(self.nurse).post(f"/api/appointments/{appt_id}/reject/", {"note": "الطبيب مسافر"}, format="json")
        self.assertEqual(r.data["status"], "REJECTED")
        self.assertTrue(Notification.objects.filter(user=self.p_user, kind="APPOINTMENT_REJECTED").exists())
        self.assertEqual(self.book(self.p2_user, start).status_code, 201)

    def test_instant_confirmation_when_approval_not_required(self):
        self.doctor.requires_approval = False
        self.doctor.save()
        r = self.book(self.p_user, self.slot())
        self.assertEqual(r.data["status"], "CONFIRMED")

    def test_invalid_times(self):
        self.assertEqual(self.book(self.p_user, self.slot(hour=15)).data["code"], "invalid_slot")
        self.assertEqual(self.book(self.p_user, self.slot(hour=10, minute=10)).data["code"], "invalid_slot")
        past = timezone.now() - dt.timedelta(days=1)
        self.assertEqual(self.book(self.p_user, past.replace(hour=10, minute=0, second=0, microsecond=0)).status_code, 400)

    def test_directory_only_doctor_is_not_bookable(self):
        r = self.book(self.p_user, self.slot(), doctor=self.directory_only)
        self.assertEqual(r.data["code"], "not_bookable")
        self.client.force_authenticate(None)
        r = self.client.get(f"/api/doctors/?specialty=ENT")
        self.assertEqual(r.data["results"][0]["can_book"], False)

    def test_patient_cancel_notifies_staff(self):
        appt_id = self.book(self.p_user, self.slot()).data["id"]
        r = self.as_(self.p_user).post(f"/api/appointments/{appt_id}/cancel/")
        self.assertEqual(r.data["status"], "CANCELLED")
        self.assertTrue(Notification.objects.filter(user=self.doc_user, kind="APPOINTMENT_CANCELLED").exists())

    def test_database_constraint_blocks_double_booking(self):
        start = self.slot()
        Appointment.objects.create(patient=self.patient2, practitioner=self.doc_user, doctor=self.doctor,
                                   start_at=start, end_at=start + dt.timedelta(minutes=30), status="PENDING")
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(patient=self.patient, practitioner=self.doc_user, doctor=self.doctor,
                                       start_at=start, end_at=start + dt.timedelta(minutes=30), status="CONFIRMED")

    def test_patients_only_see_their_appointments(self):
        self.book(self.p_user, self.slot(hour=9))
        self.book(self.p2_user, self.slot(hour=10))
        self.assertEqual(self.as_(self.p_user).get("/api/appointments/").data["count"], 1)
        self.assertEqual(self.as_(self.nurse).get("/api/appointments/").data["count"], 2)

    def test_notifications_api(self):
        self.book(self.p_user, self.slot())
        c = self.as_(self.doc_user)
        self.assertEqual(c.get("/api/notifications/unread-count/").data["count"], 1)
        c.post("/api/notifications/read-all/")
        self.assertEqual(c.get("/api/notifications/unread-count/").data["count"], 0)

    def test_doctor_sets_weekly_schedule(self):
        r = self.as_(self.doc_user).put("/api/doctors/me/availability/", [
            {"weekday": 6, "start_time": "16:00", "end_time": "18:00"},
            {"weekday": 6, "start_time": "17:00", "end_time": "19:00"}], format="json")
        self.assertEqual(r.status_code, 400)  # overlapping
        r = self.as_(self.doc_user).put("/api/doctors/me/availability/", [
            {"weekday": 6, "start_time": "16:00", "end_time": "18:00"}], format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.doctor.availability.count(), 1)


class TriageTests(Base):
    def test_rule_engine_asks_questions_then_recommends(self):
        c = self.as_(self.p_user)
        r = c.post("/api/ai/triage/", {"message": "عندي سعال وبلغم من فترة"}, format="json")
        self.assertEqual(r.status_code, 201)
        sid = r.data["id"]
        for answer in ("حوالي أسبوع", "متوسطة", "حرارة"):
            self.assertEqual(r.data["status"], "ACTIVE")
            r = c.post(f"/api/ai/triage/{sid}/reply/", {"message": answer}, format="json")
        self.assertEqual(r.data["status"], "COMPLETED")
        res = r.data["result"]
        self.assertEqual(res["specialty"], "PULMONOLOGY")
        self.assertTrue(res["recommended_tests"])
        self.assertIn("doctor_summary", res)

    def test_red_flags_go_straight_to_emergency(self):
        r = self.as_(self.p_user).post("/api/ai/triage/", {"message": "ألم صدر شديد وضيق تنفس شديد"}, format="json")
        self.assertEqual(r.data["status"], "COMPLETED")
        self.assertEqual(r.data["result"]["urgency"], "er")
        self.assertEqual(r.data["result"]["specialty"], "EMERGENCY")

    def test_triage_attached_to_booking_is_visible_to_doctor(self):
        r = self.as_(self.p_user).post("/api/ai/triage/", {"message": "ألم صدر شديد"}, format="json")
        appt = self.as_(self.p_user).post("/api/appointments/book/", {
            "doctor": self.doctor.id, "start_at": self.slot().isoformat(), "triage": r.data["id"]}, format="json")
        self.assertEqual(appt.status_code, 201, appt.data)
        detail = self.as_(self.doc_user).get(f"/api/appointments/{appt.data['id']}/").data
        self.assertEqual(detail["triage_summary"]["urgency"], "er")


class DocumentTests(Base):
    def test_documents_are_access_checked_and_sandboxed(self):
        f = SimpleUploadedFile("report.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.as_(self.doc_user).post("/api/documents/", {"patient": self.patient.id, "title": "تحليل", "file": f})
        self.assertEqual(r.status_code, 201, r.data)
        url = r.data["view_url"]
        self.assertEqual(self.as_(self.p_user).get(url).status_code, 200)
        self.assertEqual(self.as_(self.p2_user).get(url).status_code, 403)
        resp = self.as_(self.nurse).get(url)
        self.assertIn("sandbox", resp["Content-Security-Policy"])

    def test_dangerous_upload_types_rejected(self):
        f = SimpleUploadedFile("x.html", b"<script>alert(1)</script>", content_type="text/html")
        r = self.as_(self.doc_user).post("/api/documents/", {"patient": self.patient.id, "title": "x", "file": f})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(DocumentRef.objects.count(), 0)


class DashboardTests(Base):
    def test_each_role_gets_a_dashboard(self):
        self.book(self.p_user, self.slot())
        for u in (self.admin, self.doc_user, self.nurse, self.p_user):
            r = self.as_(u).get("/api/dashboard/")
            self.assertEqual(r.status_code, 200, u.username)
        self.assertEqual(self.as_(self.doc_user).get("/api/dashboard/").data["counts"]["pending"], 1)
