"""Data migration: statuses, medical IDs, doctor profiles and default working hours."""
import datetime
import secrets

from django.db import migrations

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def forwards(apps, schema_editor):
    Appointment = apps.get_model("core_app", "Appointment")
    Patient = apps.get_model("core_app", "Patient")
    DoctorProfile = apps.get_model("core_app", "DoctorProfile")
    DoctorAvailability = apps.get_model("core_app", "DoctorAvailability")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    Appointment.objects.filter(status="SCHEDULED").update(status="CONFIRMED")

    seen = set()
    for appt in Appointment.objects.filter(status__in=["PENDING", "CONFIRMED"]).order_by("created_at", "id"):
        key = (appt.practitioner_id, appt.start_at)
        if appt.practitioner_id and key in seen:
            appt.status = "CANCELLED"
            appt.decision_note = "تعارض مع موعد آخر (ترحيل بيانات)"
            appt.save(update_fields=["status", "decision_note"])
        seen.add(key)

    used = set(Patient.objects.exclude(medical_id=None).values_list("medical_id", flat=True))
    for p in Patient.objects.filter(medical_id=None):
        mid = None
        while not mid or mid in used:
            mid = "SMI-" + "".join(secrets.choice(ALPHABET) for _ in range(8))
        used.add(mid)
        p.medical_id = mid
        p.save(update_fields=["medical_id"])

    doctor_group = Group.objects.filter(name="Doctor").first()
    nurse_group = Group.objects.filter(name="Nurse").first()
    doctors = list(User.objects.filter(groups=doctor_group)) if doctor_group else []
    nurses = list(User.objects.filter(groups=nurse_group)) if nurse_group else []

    for u in doctors:
        profile, created = DoctorProfile.objects.get_or_create(
            user=u,
            defaults={"full_name": (f"{u.first_name} {u.last_name}".strip() or u.username),
                      "specialty": "GENERAL", "city": "دمشق", "is_verified": True},
        )
        if created:
            for wd in (6, 0, 1, 2, 3):  # python weekday: Mon=0 .. Sun=6
                DoctorAvailability.objects.create(doctor=profile, weekday=wd,
                                                  start_time=datetime.time(9, 0), end_time=datetime.time(14, 0))
        if nurses:
            profile.nurses.add(*nurses)
        Appointment.objects.filter(practitioner=u, doctor=None).update(doctor=profile)


class Migration(migrations.Migration):
    dependencies = [
        ("core_app", "0006_smart_identity_scheduling"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
