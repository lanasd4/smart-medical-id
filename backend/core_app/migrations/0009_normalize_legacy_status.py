"""Normalise lowercase appointment statuses."""
from django.db import migrations

MAP = {"scheduled": "CONFIRMED", "confirmed": "CONFIRMED", "pending": "PENDING", "completed": "COMPLETED",
       "cancelled": "CANCELLED", "canceled": "CANCELLED", "no_show": "NO_SHOW", "rejected": "REJECTED"}


def forwards(apps, schema_editor):
    Appointment = apps.get_model("core_app", "Appointment")
    for old, new in MAP.items():
        for appt in Appointment.objects.filter(status=old):
            clash = new in ("PENDING", "CONFIRMED") and Appointment.objects.filter(
                practitioner_id=appt.practitioner_id, start_at=appt.start_at, status__in=["PENDING", "CONFIRMED"]
            ).exclude(pk=appt.pk).exists()
            appt.status = "CANCELLED" if clash and appt.practitioner_id else new
            appt.save(update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [("core_app", "0008_active_slot_constraint")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
