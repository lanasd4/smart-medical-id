import secrets

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone

# =====================================================================
# Reference lists (shared with the frontend through /api/meta/)
# =====================================================================

SPECIALTIES = [
    ("GENERAL", "طب عام"),
    ("INTERNAL", "أمراض داخلية"),
    ("CARDIOLOGY", "أمراض القلب"),
    ("PULMONOLOGY", "الأمراض الصدرية"),
    ("GASTRO", "الجهاز الهضمي"),
    ("NEUROLOGY", "الأمراض العصبية"),
    ("PSYCHIATRY", "الطب النفسي"),
    ("DERMATOLOGY", "الجلدية"),
    ("ENT", "أذن وأنف وحنجرة"),
    ("OPHTHALMOLOGY", "العينية"),
    ("ORTHOPEDICS", "العظمية"),
    ("RHEUMATOLOGY", "المفاصل والروماتيزم"),
    ("ENDOCRINOLOGY", "الغدد الصم والسكري"),
    ("NEPHROLOGY", "الكلية"),
    ("UROLOGY", "المسالك البولية"),
    ("OBGYN", "النسائية والتوليد"),
    ("PEDIATRICS", "طب الأطفال"),
    ("GENERAL_SURGERY", "الجراحة العامة"),
    ("ONCOLOGY", "الأورام"),
    ("DENTISTRY", "طب الأسنان"),
    ("EMERGENCY", "الإسعاف والطوارئ"),
]
SPECIALTY_CODES = {code for code, _ in SPECIALTIES}

CITIES = [
    "دمشق", "ريف دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس",
    "درعا", "السويداء", "القنيطرة", "إدلب", "دير الزور", "الرقة", "الحسكة",
]

BLOOD_TYPES = [
    ("A+", "A+"), ("A-", "A-"),
    ("B+", "B+"), ("B-", "B-"),
    ("AB+", "AB+"), ("AB-", "AB-"),
    ("O+", "O+"), ("O-", "O-"),
]

DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp", "gif", "dcm", "txt", "doc", "docx", "html", "htm"]
UPLOAD_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp", "gif", "dcm", "txt", "doc", "docx"]
MAX_UPLOAD_MB = 15

_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid confusion


def generate_medical_id():
    return "SMI-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))


def validate_upload_size(f):
    if f.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f"الحد الأقصى لحجم الملف {MAX_UPLOAD_MB} ميغابايت.")

# =====================================================================
# Patient & Identifiers
# =====================================================================

class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    blood_type = models.CharField(max_length=3, null=True, blank=True, choices=BLOOD_TYPES)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # Smart medical identity number shown on the ID card
    medical_id = models.CharField(max_length=16, unique=True, null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=30, blank=True, default="")

    def save(self, *args, **kwargs):
        if not self.medical_id:
            candidate = generate_medical_id()
            while Patient.objects.filter(medical_id=candidate).exists():
                candidate = generate_medical_id()
            self.medical_id = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PatientIdentifier(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="identifiers")
    type = models.CharField(max_length=30)   # NID, MRN, PASSPORT
    value = models.CharField(max_length=100)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.type}: {self.value}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["patient", "type", "value"], name="uq_pid_type_value")
        ]

# =====================================================================
# Reference Dictionaries (ICD / LOINC / RxNorm)
# =====================================================================

class ConditionDictionary(models.Model):
    code = models.CharField(max_length=20, unique=True)   # ICD code
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.code} - {self.name}"


class ObservationDictionary(models.Model):
    code = models.CharField(max_length=50, unique=True)   # LOINC code
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.code} - {self.name}"


class MedicationDictionary(models.Model):
    code = models.CharField(max_length=50, unique=True)   # RxNorm code
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.code} - {self.name}"

# =====================================================================
# Medical Records
# =====================================================================

class Condition(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="conditions")
    code = models.ForeignKey(ConditionDictionary, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, default="")  # free text when no ICD code
    is_chronic = models.BooleanField(default=False)
    status = models.CharField(max_length=50, null=True, blank=True)  # Active, Resolved, etc.
    onset_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    @property
    def display_name(self):
        return self.name or (self.code.name if self.code_id else "")

    def clean(self):
        if not self.code_id and not self.name:
            raise ValidationError("أدخل اسم المرض أو اختر رمزه.")

    def __str__(self):
        return f"{self.patient.name} - {self.display_name}"


class Allergy(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="allergies")
    substance = models.CharField(max_length=200)
    reaction = models.CharField(max_length=200, null=True, blank=True)
    severity = models.CharField(max_length=50, null=True, blank=True)  # Mild, Moderate, Severe
    recorded_date = models.DateField(auto_now_add=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return f"{self.substance} ({self.severity})"


class Encounter(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="encounters")
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    type = models.CharField(
        max_length=50, null=True, blank=True,
        choices=[("OUTPATIENT", "Outpatient"), ("INPATIENT", "Inpatient"), ("ER", "Emergency")]
    )
    reason = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Encounter {self.id} - {self.patient.name} ({self.type})"


class Observation(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="observations")
    encounter = models.ForeignKey('Encounter', on_delete=models.SET_NULL, null=True, blank=True, related_name="observations")
    code = models.ForeignKey(ObservationDictionary, on_delete=models.SET_NULL, null=True)
    value = models.CharField(max_length=100, null=True, blank=True)
    unit = models.CharField(max_length=30, null=True, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.encounter and self.encounter.patient_id != self.patient_id:
            raise ValidationError("المريض في الـ Observation يجب أن يطابق مريض الـ Encounter.")

    def __str__(self):
        return f"{self.patient.name} - {self.code}"


class Medication(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medications")
    encounter = models.ForeignKey('Encounter', on_delete=models.SET_NULL, null=True, blank=True, related_name="medications")
    code = models.ForeignKey(MedicationDictionary, on_delete=models.SET_NULL, null=True)
    local_name = models.CharField(max_length=200, null=True, blank=True)  # اسم شائع محلي (اختياري)
    dose = models.CharField(max_length=100, null=True, blank=True)
    frequency = models.CharField(max_length=100, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=50, null=True, blank=True,
        choices=[("ACTIVE", "Active"), ("STOPPED", "Stopped"), ("COMPLETED", "Completed")]
    )
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def clean(self):
        if self.encounter and self.encounter.patient_id != self.patient_id:
            raise ValidationError("المريض في الدواء يجب أن يطابق مريض الـ Encounter.")

    def __str__(self):
        return f"{self.patient.name} - {self.code}"

# =====================================================================
# Documents & Other
# =====================================================================

class DocumentRef(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="documents")
    encounter = models.ForeignKey('Encounter', on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    doc_type = models.CharField(max_length=50, null=True, blank=True)  # LAB, RADIOLOGY, REPORT, PRESCRIPTION, OTHER
    title = models.CharField(max_length=200)
    file = models.FileField(
        upload_to="documents/%Y/%m/",
        validators=[FileExtensionValidator(DOCUMENT_EXTENSIONS), validate_upload_size],
    )
    notes = models.TextField(blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def clean(self):
        if self.encounter and self.encounter.patient_id != self.patient_id:
            raise ValidationError("المريض في الملف يجب أن يطابق مريض الـ Encounter.")

    def __str__(self):
        return self.title


class Immunization(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="immunizations")
    vaccine_name = models.CharField(max_length=200)
    administered_at = models.DateField()
    lot_number = models.CharField(max_length=100, null=True, blank=True)
    performer = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.vaccine_name} - {self.administered_at}"


class Consent(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="consents")
    status = models.CharField(
        max_length=20,
        choices=[("GRANTED", "Granted"), ("REVOKED", "Revoked")],
        default="GRANTED"
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    purpose = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"Consent ({self.status}) for {self.patient.name}"


class LoginSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="login_sessions")
    session_key = models.CharField(max_length=64, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    login_at = models.DateTimeField(auto_now_add=True)
    logout_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # اختياري: لو صارت محاولة فاشلة فينا نخزّنها
    username_attempt = models.CharField(max_length=150, null=True, blank=True)

    def __str__(self):
        who = self.user.username if self.user_id else (self.username_attempt or "Unknown")
        local_time = timezone.localtime(self.login_at) if self.login_at else None
        return f"{who} [{self.session_key}] @ {local_time:%Y-%m-%d %H:%M}"


# =====================================================================
# Doctors directory & scheduling
# =====================================================================

class DoctorProfile(models.Model):
    """A doctor in the directory. Without a linked, verified user the doctor is listed but not bookable."""
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="doctor_profile")
    full_name = models.CharField(max_length=150)
    specialty = models.CharField(max_length=30, choices=SPECIALTIES, default="GENERAL", db_index=True)
    city = models.CharField(max_length=60, db_index=True, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")
    clinic_name = models.CharField(max_length=150, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    license_number = models.CharField(max_length=60, blank=True, default="")
    years_experience = models.PositiveSmallIntegerField(null=True, blank=True)
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    is_verified = models.BooleanField(default=False, db_index=True)
    accepts_online_booking = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)  # False -> slots are confirmed instantly
    slot_minutes = models.PositiveSmallIntegerField(default=30)
    booking_window_days = models.PositiveSmallIntegerField(default=30)
    nurses = models.ManyToManyField(User, blank=True, related_name="assisted_doctors")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["specialty", "city"])]

    @property
    def is_subscribed(self):
        return bool(self.user_id) and self.is_verified and self.user.is_active

    @property
    def can_book(self):
        return self.is_subscribed and self.accepts_online_booking

    def __str__(self):
        return f"د. {self.full_name} ({self.get_specialty_display()})"


class DoctorAvailability(models.Model):
    """Weekly recurring working hours. weekday: 0=Monday ... 6=Sunday (Python convention)."""
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name="availability")
    weekday = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(7)])
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]

    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError("وقت النهاية يجب أن يكون بعد وقت البداية.")


class DoctorTimeOff(models.Model):
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name="time_off")
    date = models.DateField()
    reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["doctor", "date"], name="uq_doctor_timeoff_date")]


class Appointment(models.Model):
    PENDING, CONFIRMED, REJECTED, CANCELLED, COMPLETED, NO_SHOW = (
        "PENDING", "CONFIRMED", "REJECTED", "CANCELLED", "COMPLETED", "NO_SHOW")
    STATUS_CHOICES = [
        (PENDING, "بانتظار الموافقة"),
        (CONFIRMED, "مؤكد"),
        (REJECTED, "مرفوض"),
        (CANCELLED, "ملغى"),
        (COMPLETED, "مكتمل"),
        (NO_SHOW, "لم يحضر"),
    ]
    ACTIVE_STATUSES = (PENDING, CONFIRMED)  # statuses that hold the time slot

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
    practitioner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments"
    )
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="appointments")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=120, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    encounter = models.ForeignKey(
        Encounter, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments"
    )
    triage =models.ForeignKey("TriageSession", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="appointments")
    booked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["practitioner", "start_at"]),
            models.Index(fields=["patient", "start_at"]),
        ]
        constraints = [
            # one active booking per doctor and start time, enforced by the database
            models.UniqueConstraint(
                fields=["practitioner", "start_at"],
                condition=Q(status__in=["PENDING", "CONFIRMED"]),
                name="uq_active_slot_per_practitioner",
            ),
        ]

    def clean(self):
        if self.end_at <= self.start_at:
            raise ValidationError("وقت النهاية يجب أن يكون بعد وقت البداية.")

    def overlapping(self):
        qs = Appointment.objects.filter(
            practitioner=self.practitioner, status__in=self.ACTIVE_STATUSES,
            start_at__lt=self.end_at, end_at__gt=self.start_at,
        )
        return qs.exclude(pk=self.pk) if self.pk else qs

    def __str__(self):
        who = self.patient.name if self.patient_id else "Unknown"
        return f"Appt {who} @ {self.start_at} ({self.status})"


# =====================================================================
# Surgical history
# =====================================================================

class Procedure(models.Model):
    """Previous surgeries / procedures (العمليات السابقة)."""
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="procedures")
    name = models.CharField(max_length=200)
    performed_on = models.DateField(null=True, blank=True)
    hospital = models.CharField(max_length=150, blank=True, default="")
    surgeon = models.CharField(max_length=150, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_on", "-id"]

    def __str__(self):
        return f"{self.name} ({self.performed_on or '?'})"


# =====================================================================
# Notifications & Web Push
# =====================================================================

class Notification(models.Model):
    KINDS = [
        ("APPOINTMENT_REQUEST", "طلب موعد"),
        ("APPOINTMENT_CONFIRMED", "تأكيد موعد"),
        ("APPOINTMENT_REJECTED", "رفض موعد"),
        ("APPOINTMENT_CANCELLED", "إلغاء موعد"),
        ("APPOINTMENT_REMINDER", "تذكير بموعد"),
        ("DOCTOR_VERIFICATION", "توثيق طبيب"),
        ("SYSTEM", "النظام"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=KINDS, default="SYSTEM")
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500, blank=True, default="")
    link = models.CharField(max_length=255, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]


class PushSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


# =====================================================================
# AI triage ("smart health guide")
# =====================================================================

class TriageSession(models.Model):
    ACTIVE, COMPLETED = "ACTIVE", "COMPLETED"
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="triage_sessions")
    status = models.CharField(max_length=10, choices=[(ACTIVE, "Active"), (COMPLETED, "Completed")],
                              default=ACTIVE)
    messages = models.JSONField(default=list, blank=True)  # [{"role": "user"|"assistant", "content": str, ...}]
    result = models.JSONField(default=dict, blank=True)
    engine = models.CharField(max_length=20, default="rules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


# =====================================================================
# Audit Event Tracking
# =====================================================================

class AuditEvent(models.Model):
    """Track all system operations for compliance and debugging"""
    
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('RESTORE', 'Restore'),
        ('PURGE', 'Purge'),
        ('VIEW', 'View'),
    ]
    
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name='audit_events')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    resource = models.CharField(max_length=50, db_index=True)  # Patient, User, etc.
    resource_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'action']),
            models.Index(fields=['resource', 'resource_id']),
        ]
    
    def __str__(self):
        actor_name = self.actor.username if self.actor else 'System'
        return f"{actor_name} - {self.action} {self.resource} #{self.resource_id}"


# =====================================================================
# AI Chat History
# =====================================================================

class ChatMessage(models.Model):
    """Store AI chat conversations for each patient"""
    
    ROLE_CHOICES = [
        ('USER', 'User'),
        ('ASSISTANT', 'Assistant'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='chat_messages', db_index=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, db_index=True)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)  # Store model info, eval_count, etc.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['created_at']  # Oldest first for chronological display
        indexes = [
            models.Index(fields=['patient', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.patient.name} - {self.role} @ {self.created_at}"
