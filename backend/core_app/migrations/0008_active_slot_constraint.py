from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core_app", "0007_migrate_legacy_data")]

    operations = [
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["PENDING", "CONFIRMED"])),
                fields=("practitioner", "start_at"),
                name="uq_active_slot_per_practitioner",
            ),
        ),
    ]
