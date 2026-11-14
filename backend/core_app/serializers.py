import os

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.db import transaction
from rest_framework import serializers

from .models import (
    BLOOD_TYPES, CITIES, SPECIALTIES, UPLOAD_EXTENSIONS,
    Allergy, Appointment, AuditEvent, ChatMessage, Condition, ConditionDictionary,
    Consent, DoctorAvailability, DoctorProfile, DoctorTimeOff, DocumentRef, Encounter, Medication,
    MedicationDictionary, Notification, Observation, ObservationDictionary, Patient,
    PatientIdentifier, Procedure, TriageSession,
)

User = get_user_model()
SPECIALTY_LABELS = dict(SPECIALTIES)


def user_display(u):
    if not u:
        return None
    if hasattr(u, "doctor_profile"):
        try:
            return "د. " + u.doctor_profile.full_name
        except DoctorProfile.DoesNotExist:
            pass
    return u.get_full_name() or u.username

# =====================================================================
# Patients
# =====================================================================

class PatientIdentifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientIdentifier
        fields = ("id", "type", "value", "is_primary")


class PatientSerializer(serializers.ModelSerializer):
    identifiers = PatientIdentifierSerializer(many=True, read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True, allow_null=True)
    age = serializers.SerializerMethodField()
    # Staff can create a patient together with a login account
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = Patient
        fields = (
            "id", "medical_id", "name", "date_of_birth", "age", "gender",
            "phone", "email", "address", "blood_type", "height_cm", "weight_kg",
            "emergency_contact_name", "emergency_contact_phone",
            "identifiers", "is_active", "username", "password", "user_id",
        )
        read_only_fields = ("id", "medical_id", "is_active", "user_id")

    def get_age(self, obj):
        from .ai import _age
        return _age(obj.date_of_birth)

    def validate_username(self, value):
        if self.instance is None and value and User.objects.filter(username=value).exists():
            raise serializers.ValidationError("اسم المستخدم مستخدم مسبقاً.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        username = validated_data.pop("username", None)
        raw_password = validated_data.pop("password", None)
        user = None
        if username and raw_password:
            user = User.objects.create_user(username=username, password=raw_password,
                                            email=validated_data.get("email") or "")
            user.groups.add(Group.objects.get_or_create(name="Patient")[0])
        return Patient.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("username", None)
        validated_data.pop("password", None)
        return super().update(instance, validated_data)


class PatientSelfSerializer(serializers.ModelSerializer):
    """Fields a patient may edit themself."""
    class Meta:
        model = Patient
        fields = ("phone", "email", "address")

# =====================================================================
# Doctors directory & scheduling
# =====================================================================

class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorAvailability
        fields = ("id", "weekday", "start_time", "end_time")

    def validate(self, data):
        if data["end_time"] <= data["start_time"]:
            raise serializers.ValidationError("وقت النهاية يجب أن يكون بعد وقت البداية.")
        return data


class TimeOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorTimeOff
        fields = ("id", "date", "reason")


class DoctorPublicSerializer(serializers.ModelSerializer):
    specialty_label = serializers.CharField(source="get_specialty_display", read_only=True)
    is_subscribed = serializers.BooleanField(read_only=True)
    can_book = serializers.BooleanField(read_only=True)
    availability = AvailabilitySerializer(many=True, read_only=True)

    class Meta:
        model = DoctorProfile
        fields = ("id", "user_id", "full_name", "specialty", "specialty_label", "city", "address", "clinic_name",
                  "phone", "bio", "years_experience", "consultation_fee", "is_subscribed", "can_book",
                  "requires_approval", "slot_minutes", "booking_window_days", "availability")


class DoctorAdminSerializer(DoctorPublicSerializer):
    username = serializers.CharField(source="user.username", read_only=True, allow_null=True)
    nurses = serializers.PrimaryKeyRelatedField(many=True, required=False,
                                                queryset=User.objects.filter(groups__name="Nurse"))
    nurse_names = serializers.SerializerMethodField()

    class Meta(DoctorPublicSerializer.Meta):
        fields = DoctorPublicSerializer.Meta.fields + (
            "user", "username", "is_verified", "accepts_online_booking", "license_number",
            "nurses", "nurse_names", "created_at")
        read_only_fields = ("created_at",)
        extra_kwargs = {"user": {"required": False, "allow_null": True,
                                 "queryset": User.objects.filter(groups__name="Doctor")}}

    def get_nurse_names(self, obj):
        return [n.get_full_name() or n.username for n in obj.nurses.all()]


class DoctorSelfSerializer(serializers.ModelSerializer):
    specialty_label = serializers.CharField(source="get_specialty_display", read_only=True)
    availability = AvailabilitySerializer(many=True, read_only=True)
    time_off = TimeOffSerializer(many=True, read_only=True)
    nurse_names = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = ("id", "full_name", "specialty", "specialty_label", "city", "address", "clinic_name",
                  "phone", "bio", "license_number", "years_experience", "consultation_fee",
                  "is_verified", "accepts_online_booking", "requires_approval", "slot_minutes",
                  "booking_window_days", "availability", "time_off", "nurse_names")
        read_only_fields = ("is_verified",)

    def get_nurse_names(self, obj):
        return [n.get_full_name() or n.username for n in obj.nurses.all()]

    def validate_slot_minutes(self, v):
        if v not in (10, 15, 20, 30, 45, 60):
            raise serializers.ValidationError("مدة الموعد يجب أن تكون 10 أو 15 أو 20 أو 30 أو 45 أو 60 دقيقة.")
        return v

    def validate_booking_window_days(self, v):
        if not 1 <= v <= 120:
            raise serializers.ValidationError("بين 1 و 120 يوماً.")
        return v


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_medical_id = serializers.CharField(source="patient.medical_id", read_only=True)
    practitioner_name = serializers.CharField(source="practitioner.username", read_only=True)
    practitioner_full_name = serializers.SerializerMethodField()
    doctor_specialty = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    decided_by_name = serializers.SerializerMethodField()
    triage_summary = serializers.SerializerMethodField()

    # Staff quick-booking for a walk-in patient
    new_patient_name = serializers.CharField(write_only=True, required=False)
    new_patient_phone = serializers.CharField(write_only=True, required=False)
    new_patient_email = serializers.EmailField(write_only=True, required=False)

    class Meta:
        model = Appointment
        fields = (
            "id", "patient", "patient_name", "patient_medical_id",
            "practitioner", "practitioner_name", "practitioner_full_name", "doctor", "doctor_specialty",
            "start_at", "end_at", "reason", "location", "status", "status_label",
            "decision_note", "decided_by_name", "decided_at", "triage", "triage_summary",
            "encounter", "created_at",
            "new_patient_name", "new_patient_phone", "new_patient_email",
        )
        read_only_fields = ("status", "doctor", "decided_at", "decision_note", "triage")
        extra_kwargs = {"patient": {"required": False}}

    def get_practitioner_full_name(self, obj):
        if obj.doctor_id:
            return obj.doctor.full_name
        if obj.practitioner_id:
            return obj.practitioner.get_full_name() or obj.practitioner.username
        return None

    def get_doctor_specialty(self, obj):
        return obj.doctor.get_specialty_display() if obj.doctor_id else None

    def get_decided_by_name(self, obj):
        return user_display(obj.decided_by) if obj.decided_by_id else None

    def get_triage_summary(self, obj):
        if not obj.triage_id or not obj.triage.result:
            return None
        r = obj.triage.result
        return {"specialty_label": r.get("specialty_label"), "urgency": r.get("urgency"),
                "doctor_summary": r.get("doctor_summary"), "possible_conditions": r.get("possible_conditions"),
                "recommended_tests": r.get("recommended_tests")}

    def validate(self, data):
        if self.instance is None and not data.get("patient") and not data.get("new_patient_name"):
            raise serializers.ValidationError({"patient": "اختر مريضاً أو أدخل بيانات مريض جديد."})
        start_at = data.get("start_at", getattr(self.instance, "start_at", None))
        end_at = data.get("end_at", getattr(self.instance, "end_at", None))
        practitioner = data.get("practitioner", getattr(self.instance, "practitioner", None))
        if start_at and end_at:
            if end_at <= start_at:
                raise serializers.ValidationError({"end_at": "وقت النهاية يجب أن يكون بعد البداية."})
            if practitioner:
                conflicts = Appointment.objects.filter(
                    practitioner=practitioner, status__in=Appointment.ACTIVE_STATUSES,
                    start_at__lt=end_at, end_at__gt=start_at)
                if self.instance:
                    conflicts = conflicts.exclude(pk=self.instance.pk)
                c = conflicts.first()
                if c:
                    raise serializers.ValidationError({"start_at":
                        f"تعارض: يوجد موعد من {c.start_at.astimezone().strftime('%H:%M')} إلى {c.end_at.astimezone().strftime('%H:%M')}"})
        return data

    def create(self, validated_data):
        name = validated_data.pop("new_patient_name", None)
        phone = validated_data.pop("new_patient_phone", None)
        email = validated_data.pop("new_patient_email", None)
        if name and not validated_data.get("patient"):
            validated_data["patient"] = Patient.objects.create(name=name, phone=phone, email=email)
        practitioner = validated_data.get("practitioner")
        if practitioner is not None and not validated_data.get("doctor"):
            validated_data["doctor"] = DoctorProfile.objects.filter(user=practitioner).first()
        return super().create(validated_data)


class BookingSerializer(serializers.Serializer):
    doctor = serializers.PrimaryKeyRelatedField(queryset=DoctorProfile.objects.all())
    start_at = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    triage = serializers.PrimaryKeyRelatedField(queryset=TriageSession.objects.all(), required=False, allow_null=True)
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all(), required=False)  # staff only

# =====================================================================
# Medical records
# =====================================================================

class _PatientOptional:
    """patient is optional on create: a patient user writes to their own record automatically."""
    extra = {"patient": {"required": False}}


class EncounterSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    conditions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ConditionDictionary.objects.all(), write_only=True, required=False)

    class Meta:
        model = Encounter
        fields = ("id", "patient", "patient_name", "start_at", "end_at", "type", "reason", "conditions")
        extra_kwargs = _PatientOptional.extra

    def validate(self, data):
        if not data.get("start_at") and not self.instance:
            from django.utils import timezone
            data["start_at"] = timezone.now()
        return data

    def create(self, validated_data):
        codes = validated_data.pop("conditions", [])
        encounter = super().create(validated_data)
        for code in codes:
            Condition.objects.create(patient=encounter.patient, code=code, status="Active",
                                     onset_date=encounter.start_at.date() if encounter.start_at else None)
        return encounter


class _EncounterMatch:
    def validate(self, data):
        encounter = data.get("encounter")
        patient = data.get("patient")
        if encounter and patient and encounter.patient_id != patient.id:
            raise serializers.ValidationError({"encounter": "الزيارة يجب أن تكون لنفس المريض."})
        return data


class ObservationSerializer(_EncounterMatch, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    code_name = serializers.CharField(source="code.name", read_only=True, default=None)

    class Meta:
        model = Observation
        fields = ("id", "patient", "patient_name", "encounter", "code", "code_name", "value", "unit", "observed_at")
        extra_kwargs = _PatientOptional.extra

    def validate(self, data):
        data = super().validate(data)
        if not data.get("observed_at") and not self.instance:
            from django.utils import timezone
            data["observed_at"] = timezone.now()
        return data


class MedicationSerializer(_EncounterMatch, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    code_name = serializers.CharField(source="code.name", read_only=True, default=None)
    medication_name = serializers.SerializerMethodField()
    added_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Medication
        fields = ("id", "patient", "patient_name", "encounter", "code", "code_name", "medication_name",
                  "local_name", "dose", "frequency", "start_date", "end_date", "status", "added_by_name")
        extra_kwargs = _PatientOptional.extra

    def get_medication_name(self, obj):
        return obj.local_name or (obj.code.name if obj.code_id else f"دواء #{obj.id}")

    def get_added_by_name(self, obj):
        return user_display(obj.added_by) if obj.added_by_id else None

    def validate(self, data):
        data = super().validate(data)
        if not self.instance:
            if not data.get("local_name") and not data.get("code"):
                raise serializers.ValidationError({"local_name": "أدخل اسم الدواء."})
            from django.utils import timezone
            data.setdefault("start_date", timezone.localdate())
            data["status"] = data.get("status") or "ACTIVE"
        return data


class ConditionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    code_name = serializers.CharField(source="code.name", read_only=True, default=None)
    display_name = serializers.CharField(read_only=True)
    added_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Condition
        fields = ("id", "patient", "patient_name", "code", "code_name", "name", "display_name",
                  "is_chronic", "status", "onset_date", "notes", "added_by_name")
        extra_kwargs = _PatientOptional.extra

    def get_added_by_name(self, obj):
        return user_display(obj.added_by) if obj.added_by_id else None

    def validate(self, data):
        if not self.instance and not data.get("code") and not (data.get("name") or "").strip():
            raise serializers.ValidationError({"name": "أدخل اسم المرض."})
        return data


class AllergySerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)

    class Meta:
        model = Allergy
        fields = ("id", "patient", "patient_name", "substance", "reaction", "severity", "recorded_date")
        extra_kwargs = _PatientOptional.extra


class ProcedureSerializer(serializers.ModelSerializer):
    added_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Procedure
        fields = ("id", "patient", "name", "performed_on", "hospital", "surgeon", "notes", "added_by_name", "created_at")
        extra_kwargs = _PatientOptional.extra

    def get_added_by_name(self, obj):
        return user_display(obj.added_by) if obj.added_by_id else None


class DocumentRefSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    view_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    added_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentRef
        fields = ("id", "patient", "patient_name", "encounter", "doc_type", "title", "notes",
                  "file", "view_url", "file_name", "file_size", "uploaded_at", "added_by_name")
        extra_kwargs = {"patient": {"required": False}, "file": {"write_only": True}}

    def get_view_url(self, obj):
        return f"/api/documents/{obj.id}/view/"

    def get_file_name(self, obj):
        return os.path.basename(obj.file.name) if obj.file else None

    def get_file_size(self, obj):
        try:
            return obj.file.size if obj.file else None
        except (OSError, ValueError):
            return None

    def get_added_by_name(self, obj):
        return user_display(obj.added_by) if obj.added_by_id else None

    def validate_file(self, f):
        ext = os.path.splitext(f.name)[1].lower().lstrip(".")
        if ext not in UPLOAD_EXTENSIONS:
            raise serializers.ValidationError("نوع الملف غير مسموح. المسموح: " + "، ".join(UPLOAD_EXTENSIONS))
        return f


class ConsentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)

    class Meta:
        model = Consent
        fields = ("id", "patient", "patient_name", "status", "valid_from", "valid_to", "purpose")


class ConditionDictionarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ConditionDictionary
        fields = ("id", "code", "name")


class ObservationDictionarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ObservationDictionary
        fields = ("id", "code", "name")


class MedicationDictionarySerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicationDictionary
        fields = ("id", "code", "name")


AdminConditionDictionarySerializer = ConditionDictionarySerializer
AdminObservationDictionarySerializer = ObservationDictionarySerializer
AdminMedicationDictionarySerializer = MedicationDictionarySerializer


class MeSerializer(serializers.Serializer):
    patient = PatientSerializer()
    appointments = AppointmentSerializer(many=True)
    encounters = EncounterSerializer(many=True)
    observations = ObservationSerializer(many=True)
    medications = MedicationSerializer(many=True)
    conditions = ConditionSerializer(many=True)
    allergies = AllergySerializer(many=True)
    procedures = ProcedureSerializer(many=True)
    documents = DocumentRefSerializer(many=True)

# =====================================================================
# Notifications, triage
# =====================================================================

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "kind", "title", "body", "link", "is_read", "created_at")
        read_only_fields = fields


class TriageSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TriageSession
        fields = ("id", "status", "messages", "result", "engine", "created_at", "updated_at")
        read_only_fields = fields

# =====================================================================
# Registration & users
# =====================================================================

class RegisterSerializer(serializers.Serializer):
    """Doctor self-registration. The account gets no role until an admin verifies it."""
    role = serializers.ChoiceField(choices=["doctor"], default="doctor")
    username = serializers.RegexField(r"^[\w.@+-]{3,150}$", error_messages={
        "invalid": "اسم المستخدم: أحرف إنكليزية وأرقام و . _ - فقط (3 أحرف على الأقل)."})
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    specialty = serializers.ChoiceField(choices=[c for c, _ in SPECIALTIES])
    city = serializers.CharField(max_length=60)
    clinic_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    license_number = serializers.CharField(max_length=60)

    def validate_username(self, v):
        if User.objects.filter(username__iexact=v).exists():
            raise serializers.ValidationError("اسم المستخدم مستخدم مسبقاً.")
        return v

    def validate(self, data):
        user = User(username=data["username"], email=data.get("email", ""), first_name=data["first_name"])
        try:
            password_validation.validate_password(data["password"], user)
        except Exception as exc:
            raise serializers.ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))})
        return data

    @transaction.atomic
    def create(self, data):
        user = User.objects.create_user(
            username=data["username"], password=data["password"], email=data.get("email") or "",
            first_name=data["first_name"], last_name=data.get("last_name") or "",
        )
        DoctorProfile.objects.create(
            user=user, full_name=f"{data['first_name']} {data.get('last_name') or ''}".strip(),
            specialty=data["specialty"], city=data["city"], clinic_name=data.get("clinic_name", ""),
            address=data.get("address", ""), phone=data.get("phone", ""),
            license_number=data["license_number"], is_verified=False,
        )
        return user


class UserAdminSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=["Admin", "Doctor", "Nurse", "Patient"], required=False, write_only=True)
    groups = serializers.ListField(child=serializers.CharField(), required=False, write_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    patient_profile = serializers.DictField(required=False, write_only=True)
    doctor_profile = serializers.DictField(required=False, write_only=True)
    groups_display = serializers.SerializerMethodField()
    doctor_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_active", "is_staff",
                  "is_superuser", "password", "role", "groups", "patient_profile", "doctor_profile",
                  "groups_display", "doctor_profile_id", "date_joined", "last_login"]
        read_only_fields = ["id", "is_superuser", "date_joined", "last_login"]

    def get_groups_display(self, obj):
        return [g.name for g in obj.groups.all()]

    def get_doctor_profile_id(self, obj):
        try:
            return obj.doctor_profile.id
        except DoctorProfile.DoesNotExist:
            return None

    def _apply_role(self, user, role, groups_names):
        names = [role] if role else (groups_names if isinstance(groups_names, list) else None)
        if not names:
            return
        user.groups.clear()
        for name in names:
            user.groups.add(Group.objects.get_or_create(name=name)[0])
        if any(n in ("Admin", "Doctor", "Nurse") for n in names):
            user.is_staff = True
            user.save(update_fields=["is_staff"])

    def _ensure_profiles(self, user, role, patient_profile, doctor_profile):
        if role == "Patient" and not Patient.objects.filter(user=user).exists():
            allowed = {"name", "date_of_birth", "gender", "phone", "email", "address", "blood_type", "height_cm", "weight_kg"}
            data = {k: v for k, v in (patient_profile or {}).items() if k in allowed}
            data.setdefault("name", user.get_full_name() or user.get_username())
            Patient.objects.create(user=user, **data)
        if role == "Doctor" and not DoctorProfile.objects.filter(user=user).exists():
            allowed = {"specialty", "city", "address", "clinic_name", "phone", "license_number"}
            data = {k: v for k, v in (doctor_profile or {}).items() if k in allowed}
            DoctorProfile.objects.create(user=user, full_name=user.get_full_name() or user.username,
                                         is_verified=True, **data)

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data.pop("role", None)
        groups = validated_data.pop("groups", None)
        password = validated_data.pop("password", None)
        patient_profile = validated_data.pop("patient_profile", None)
        doctor_profile = validated_data.pop("doctor_profile", None)
        user = User(**validated_data)
        if password:
            password_validation.validate_password(password, user)
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        self._apply_role(user, role, groups)
        self._ensure_profiles(user, role, patient_profile, doctor_profile)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        role = validated_data.pop("role", None)
        groups = validated_data.pop("groups", None)
        password = validated_data.pop("password", None)
        validated_data.pop("patient_profile", None)
        doctor_profile = validated_data.pop("doctor_profile", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        self._apply_role(instance, role, groups)
        self._ensure_profiles(instance, role, None, doctor_profile)
        return instance


class AuditEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, allow_null=True)

    class Meta:
        model = AuditEvent
        fields = ["id", "actor", "actor_username", "action", "resource", "resource_id", "metadata", "ip", "created_at"]
        read_only_fields = fields


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "patient", "role", "message", "metadata", "created_at"]
        read_only_fields = fields


META = {
    "specialties": [{"code": c, "label": l} for c, l in SPECIALTIES],
    "cities": CITIES,
    "blood_types": [b for b, _ in BLOOD_TYPES],
    "appointment_statuses": [{"code": c, "label": l} for c, l in Appointment.STATUS_CHOICES],
    "upload_extensions": UPLOAD_EXTENSIONS,
}
