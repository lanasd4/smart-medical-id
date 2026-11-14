"""REST API views."""
import datetime as dt
import mimetypes
import os

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import ai, scheduling
from .access import (
    PATIENT_EDITABLE_FIELDS, STAFF, accessible_patients, appointments_visible_to, can_manage_appointment,
    can_view_patient, can_write_records, doctor_users_for, in_roles, is_admin, patient_of, role_of,
)
from .models import (
    Allergy, Appointment, AuditEvent, ChatMessage, Condition, ConditionDictionary,
    Consent, DoctorAvailability, DoctorProfile, DoctorTimeOff, DocumentRef, Encounter, Medication,
    MedicationDictionary, Notification, Observation, ObservationDictionary, Patient, Procedure,
    PushSubscription, TriageSession,
)
from .notify import notify, vapid_keys
from .serializers import (
    META, AllergySerializer, AppointmentSerializer, AuditEventSerializer,
    AvailabilitySerializer, BookingSerializer, ChatMessageSerializer, ConditionDictionarySerializer,
    ConditionSerializer, ConsentSerializer, DoctorAdminSerializer, DoctorPublicSerializer,
    DoctorSelfSerializer, DocumentRefSerializer, EncounterSerializer, MedicationDictionarySerializer,
    MedicationSerializer, MeSerializer, NotificationSerializer, ObservationDictionarySerializer,
    ObservationSerializer, PatientSelfSerializer, PatientSerializer, ProcedureSerializer,
    RegisterSerializer, TimeOffSerializer, TriageSessionSerializer, UserAdminSerializer,
)

User = get_user_model()


def _require(cond, msg="غير مسموح"):
    if not cond:
        raise PermissionDenied(msg)


def _audit(request, action_name, resource, resource_id, details=""):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None
    AuditEvent.objects.create(actor=request.user, action=action_name, resource=resource, ip=ip,
                              resource_id=str(resource_id), metadata={"details": details} if details else {})


def _scheduling_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except scheduling.BookingError as exc:
        raise ValidationError({"detail": exc.message, "code": exc.code})

# =====================================================================
# Auth & identity
# =====================================================================

def identity_payload(user):
    role = role_of(user)
    if not role and DoctorProfile.objects.filter(user=user, is_verified=False).exists():
        role = "PendingDoctor"  # self-registered doctor waiting for admin verification (no permissions yet)
    data = {
        "id": user.id, "username": user.get_username(), "email": user.email,
        "first_name": user.first_name, "last_name": user.last_name,
        "full_name": user.get_full_name() or user.username,
        "role": role or "Unknown", "groups": [g.name for g in user.groups.all()],
        "is_superuser": user.is_superuser,
    }
    if role == "Patient":
        p = patient_of(user)
        data["patient_id"] = p.id if p else None
        data["medical_id"] = p.medical_id if p else None
        if p:
            data["full_name"] = p.name
    if role in ("Doctor", "PendingDoctor"):
        prof = DoctorProfile.objects.filter(user=user).first()
        data["doctor_profile_id"] = prof.id if prof else None
        data["is_verified"] = bool(prof and prof.is_verified)
        if prof:
            data["full_name"] = "د. " + prof.full_name
            data["specialty_label"] = prof.get_specialty_display()
    if role == "Nurse":
        data["assisted_doctors"] = list(DoctorProfile.objects.filter(nurses=user).values("id", "full_name"))
    return data


class SmartTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = identity_payload(self.user)
        return data


class SmartTokenObtainPairView(TokenObtainPairView):
    serializer_class = SmartTokenSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        admins = User.objects.filter(Q(is_superuser=True) | Q(groups__name="Admin"), is_active=True).distinct()
        notify(list(admins), "طبيب جديد بانتظار التوثيق",
               f"د. {user.get_full_name()} سجّل في النظام ويحتاج توثيق الحساب", "DOCTOR_VERIFICATION",
               "/admin/doctors.html")
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh),
                         "user": identity_payload(user)}, status=201)


class WhoAmIView(APIView):
    def get(self, request):
        return Response(identity_payload(request.user))


class ChangeOwnPasswordView(APIView):
    def post(self, request):
        from django.contrib.auth import password_validation
        old, new = request.data.get("old_password", ""), request.data.get("new_password", "")
        if not request.user.check_password(old):
            raise ValidationError({"old_password": "كلمة المرور الحالية غير صحيحة."})
        try:
            password_validation.validate_password(new, request.user)
        except Exception as exc:
            raise ValidationError({"new_password": list(getattr(exc, "messages", [str(exc)]))})
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        return Response({"detail": "تم تغيير كلمة المرور."})


class MetaView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(META)

# =====================================================================
# Dashboard
# =====================================================================

def _my_schedule(user, qs):
    """Doctor: own appointments. Nurse: assigned doctors' appointments (all if not assigned)."""
    doctors = doctor_users_for(user)
    if role_of(user) == "Nurse" and not doctors.exists():
        return qs
    return qs.filter(practitioner__in=doctors)



class DashboardView(APIView):
    def get(self, request):
        user, role = request.user, role_of(request.user)
        now = timezone.now()
        today = timezone.localdate()
        day_start = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
        week_end = day_start + dt.timedelta(days=7)
        unread = Notification.objects.filter(user=user, is_read=False).count()
        out = {"role": role, "unread_notifications": unread}
        appt_qs = Appointment.objects.select_related("patient", "doctor", "practitioner")

        if role == "Patient":
            p = patient_of(user)
            if not p:
                return Response(out)
            upcoming = appt_qs.filter(patient=p, status__in=Appointment.ACTIVE_STATUSES, start_at__gte=now).order_by("start_at")
            out.update({
                "patient": PatientSerializer(p).data,
                "upcoming_appointments": AppointmentSerializer(upcoming[:5], many=True).data,
                "counts": {
                    "conditions": Condition.objects.filter(patient=p).count(),
                    "chronic": Condition.objects.filter(patient=p, is_chronic=True).count(),
                    "medications_active": Medication.objects.filter(patient=p, status="ACTIVE").count(),
                    "allergies": Allergy.objects.filter(patient=p).count(),
                    "documents": DocumentRef.objects.filter(patient=p).count(),
                    "procedures": Procedure.objects.filter(patient=p).count(),
                },
                "allergies": list(Allergy.objects.filter(patient=p).values("substance", "severity")[:10]),
                "chronic_conditions": [c.display_name for c in Condition.objects.filter(patient=p, is_chronic=True).select_related("code")[:10]],
                "active_medications": [m.local_name or (m.code.name if m.code_id else "") for m in
                                       Medication.objects.filter(patient=p, status="ACTIVE").select_related("code")[:10]],
            })
            return Response(out)

        if role in ("Doctor", "Nurse"):
            mine = _my_schedule(user, appt_qs)
            out.update({
                "counts": {
                    "today": mine.filter(start_at__gte=day_start, start_at__lt=day_start + dt.timedelta(days=1),
                                         status__in=Appointment.ACTIVE_STATUSES + (Appointment.COMPLETED,)).count(),
                    "pending": mine.filter(status=Appointment.PENDING, start_at__gte=now).count(),
                    "week": mine.filter(start_at__gte=day_start, start_at__lt=week_end, status=Appointment.CONFIRMED).count(),
                    "patients": Patient.objects.filter(is_active=True).count(),
                    "my_patients": mine.values("patient").distinct().count(),
                },
                "today": AppointmentSerializer(
                    mine.filter(start_at__gte=day_start, start_at__lt=day_start + dt.timedelta(days=1))
                    .exclude(status__in=[Appointment.REJECTED, Appointment.CANCELLED]).order_by("start_at"), many=True).data,
                "pending": AppointmentSerializer(
                    mine.filter(status=Appointment.PENDING, start_at__gte=now).order_by("start_at")[:10], many=True).data,
            })
            if role == "Doctor":
                prof = DoctorProfile.objects.filter(user=user).first()
                out["profile"] = DoctorSelfSerializer(prof).data if prof else None
            return Response(out)

        if role == "Admin":
            series = (Appointment.objects.filter(start_at__gte=day_start - dt.timedelta(days=7),
                                                 start_at__lt=day_start + dt.timedelta(days=8))
                      .exclude(status__in=[Appointment.REJECTED, Appointment.CANCELLED])
                      .annotate(d=TruncDay("start_at")).values("d").annotate(c=Count("id")).order_by("d"))
            out.update({
                "counts": {
                    "users": User.objects.count(),
                    "patients": Patient.objects.filter(is_active=True).count(),
                    "doctors_total": DoctorProfile.objects.count(),
                    "doctors_subscribed": DoctorProfile.objects.filter(user__isnull=False, is_verified=True).count(),
                    "doctors_pending_verification": DoctorProfile.objects.filter(user__isnull=False, is_verified=False).count(),
                    "appointments_today": Appointment.objects.filter(start_at__gte=day_start, start_at__lt=day_start + dt.timedelta(days=1)).count(),
                    "appointments_pending": Appointment.objects.filter(status=Appointment.PENDING).count(),
                    "triage_sessions": TriageSession.objects.count(),
                },
                "appointments_by_status": list(Appointment.objects.values("status").annotate(count=Count("id")).order_by("status")),
                "doctors_by_specialty": list(DoctorProfile.objects.values("specialty").annotate(count=Count("id")).order_by("-count")[:10]),
                "appointments_series": [{"date": r["d"].date().isoformat(), "count": r["c"]} for r in series if r["d"]],
            })
        return Response(out)

# =====================================================================
# Patients
# =====================================================================

class PatientViewSet(viewsets.ModelViewSet):
    serializer_class = PatientSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "email", "phone", "medical_id"]
    ordering_fields = ["id", "name", "date_of_birth"]
    filterset_fields = {"is_active": ["exact"], "gender": ["exact"], "blood_type": ["exact"]}

    def get_queryset(self):
        qs = accessible_patients(self.request.user).select_related("user").prefetch_related("identifiers").order_by("name")
        include_inactive = self.request.query_params.get("include_inactive") in ("1", "true", "True")
        if not (include_inactive and in_roles(self.request.user, STAFF)):
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        _require(in_roles(self.request.user, STAFF), "إنشاء مريض مسموح للكادر الطبي فقط.")
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        if role_of(user) == "Patient":  # a patient may change only their contact details
            for k in list(serializer.validated_data):
                if k not in PATIENT_EDITABLE_FIELDS:
                    serializer.validated_data.pop(k)
        else:
            _require(in_roles(user, STAFF))
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        _require(is_admin(request.user), "تعطيل المريض مسموح للمشرف فقط.")
        patient = self.get_object()
        patient.is_active = False
        patient.save(update_fields=["is_active"])
        return Response(status=204)

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        p = patient_of(request.user)
        if not p:
            return Response({"detail": "patient_not_found_for_user"}, status=404)
        if request.method == "PATCH":
            ser = PatientSelfSerializer(p, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
        return Response(PatientSerializer(p).data)

    @action(detail=True, methods=["get"], url_path="record")
    def record(self, request, pk=None):
        """Full medical record of one patient (for doctors/nurses with access)."""
        p = self.get_object()
        _audit(request, "VIEW", "PatientRecord", p.id)
        return Response(_full_record(p))

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        _require(is_admin(request.user))
        p = get_object_or_404(Patient, pk=pk)
        p.is_active = True
        p.save(update_fields=["is_active"])
        return Response(PatientSerializer(p).data)

    @action(detail=True, methods=["delete"], url_path="purge")
    def purge(self, request, pk=None):
        _require(is_admin(request.user), "الحذف النهائي مسموح للمشرف فقط.")
        get_object_or_404(Patient, pk=pk).delete()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="change-password")
    def change_password(self, request, pk=None):
        _require(is_admin(request.user))
        p = get_object_or_404(Patient, pk=pk)
        if not p.user_id:
            raise ValidationError({"detail": "هذا المريض ليس لديه حساب دخول."})
        new = request.data.get("new_password") or ""
        if len(new) < 8:
            raise ValidationError({"new_password": "8 أحرف على الأقل."})
        p.user.set_password(new)
        p.user.save(update_fields=["password"])
        _audit(request, "UPDATE", "Patient", p.id, "password changed by admin")
        return Response({"detail": "تم تغيير كلمة المرور."})

    @action(detail=True, methods=["post"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        _require(is_admin(request.user))
        p = get_object_or_404(Patient, pk=pk)
        p.is_active = not p.is_active
        p.save(update_fields=["is_active"])
        _audit(request, "UPDATE", "Patient", p.id, f"is_active={p.is_active}")
        return Response({"is_active": p.is_active})


def _full_record(p):
    rel = lambda qs: qs.filter(patient=p)
    return {
        "patient": PatientSerializer(p).data,
        "conditions": ConditionSerializer(rel(Condition.objects.select_related("code", "added_by")).order_by("-is_chronic", "-id"), many=True).data,
        "allergies": AllergySerializer(rel(Allergy.objects.all()).order_by("-id"), many=True).data,
        "medications": MedicationSerializer(rel(Medication.objects.select_related("code", "added_by")).order_by("-id"), many=True).data,
        "procedures": ProcedureSerializer(rel(Procedure.objects.select_related("added_by")), many=True).data,
        "observations": ObservationSerializer(rel(Observation.objects.select_related("code")).order_by("-observed_at")[:100], many=True).data,
        "encounters": EncounterSerializer(rel(Encounter.objects.all()).order_by("-start_at")[:50], many=True).data,
        "documents": DocumentRefSerializer(rel(DocumentRef.objects.select_related("added_by")).order_by("-uploaded_at"), many=True).data,
        "appointments": AppointmentSerializer(rel(Appointment.objects.select_related("doctor", "practitioner", "triage")).order_by("-start_at")[:30], many=True).data,
        "triage": TriageSessionSerializer(rel(TriageSession.objects.filter(status=TriageSession.COMPLETED))[:5], many=True).data,
    }


class MeView(APIView):
    """Complete record of the logged-in patient."""
    def get(self, request):
        p = patient_of(request.user)
        if not p:
            return Response({"detail": "patient_not_found_for_user"}, status=404)
        return Response(_full_record(p))

# =====================================================================
# Medical records
# =====================================================================

class PatientScopedViewSet(viewsets.ModelViewSet):
    """Read: staff see all patients, a patient sees their own. Write: staff. Delete: `delete_roles`."""
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {"patient": ["exact"]}
    select_related = ("patient",)
    has_added_by = False
    delete_roles = STAFF
    delete_message = "لا تملك صلاحية الحذف."

    def get_queryset(self):
        qs = self.queryset.model.objects.select_related(*self.select_related)
        if role_of(self.request.user) == "Patient":
            qs = qs.filter(patient__user=self.request.user)
        elif not in_roles(self.request.user, STAFF):
            return qs.none()
        return qs.order_by(*self.ordering)

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            _require(can_write_records(request.user), "تعديل السجل الطبي مسموح للكادر الطبي فقط.")

    def perform_create(self, serializer):
        if not serializer.validated_data.get("patient"):
            raise ValidationError({"patient": "حدد المريض."})
        serializer.save(**({"added_by": self.request.user} if self.has_added_by else {}))

    def perform_update(self, serializer):
        if "patient" in serializer.validated_data and serializer.validated_data["patient"] != serializer.instance.patient:
            raise ValidationError({"patient": "لا يمكن نقل السجل لمريض آخر."})
        serializer.save()

    def perform_destroy(self, instance):
        _require(in_roles(self.request.user, self.delete_roles), self.delete_message)
        instance.delete()


class EncounterViewSet(PatientScopedViewSet):
    queryset = Encounter.objects.all()
    serializer_class = EncounterSerializer
    ordering = ("-start_at", "-id")
    search_fields = ["reason", "type"]
    delete_roles = ("Admin",)
    delete_message = "حذف الزيارة مسموح للمشرف فقط."


class ObservationViewSet(PatientScopedViewSet):
    queryset = Observation.objects.all()
    serializer_class = ObservationSerializer
    select_related = ("patient", "code", "encounter")
    ordering = ("-observed_at", "-id")
    filterset_fields = {"patient": ["exact"], "code": ["exact"], "encounter": ["exact"]}


class MedicationViewSet(PatientScopedViewSet):
    queryset = Medication.objects.all()
    serializer_class = MedicationSerializer
    select_related = ("patient", "code", "encounter", "added_by")
    ordering = ("-id",)
    has_added_by = True
    search_fields = ["local_name", "dose"]
    filterset_fields = {"patient": ["exact"], "status": ["exact"]}
    delete_roles = ("Admin", "Doctor")
    delete_message = "حذف الأدوية مسموح للإدمن أو الطبيب فقط."


class ConditionViewSet(PatientScopedViewSet):
    queryset = Condition.objects.all()
    serializer_class = ConditionSerializer
    select_related = ("patient", "code", "added_by")
    ordering = ("-is_chronic", "-id")
    has_added_by = True
    filterset_fields = {"patient": ["exact"], "is_chronic": ["exact"], "status": ["exact"]}


class AllergyViewSet(PatientScopedViewSet):
    queryset = Allergy.objects.all()
    serializer_class = AllergySerializer
    ordering = ("-id",)
    has_added_by = True
    search_fields = ["substance", "reaction"]
    delete_roles = ("Admin",)
    delete_message = "حذف الحساسية مسموح للإدمن فقط."


class ProcedureViewSet(PatientScopedViewSet):
    queryset = Procedure.objects.all()
    serializer_class = ProcedureSerializer
    select_related = ("patient", "added_by")
    ordering = ("-performed_on", "-id")
    has_added_by = True


class DocumentRefViewSet(PatientScopedViewSet):
    queryset = DocumentRef.objects.all()
    serializer_class = DocumentRefSerializer
    select_related = ("patient", "added_by")
    ordering = ("-uploaded_at",)
    has_added_by = True
    search_fields = ["title", "doc_type"]
    filterset_fields = {"patient": ["exact"], "doc_type": ["exact"]}

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        if instance.file:
            instance.file.delete(save=False)


class ConsentViewSet(PatientScopedViewSet):  # legacy, kept for compatibility
    queryset = Consent.objects.all()
    serializer_class = ConsentSerializer
    ordering = ("-id",)


class ServeDocumentView(APIView):
    """Serves a document after an access check, sandboxed so uploaded files cannot run scripts."""
    def get(self, request, doc_id):
        doc = get_object_or_404(DocumentRef.objects.select_related("patient"), id=doc_id)
        _require(can_view_patient(request.user, doc.patient), "لا تملك صلاحية عرض هذا الملف.")
        if not doc.file or not os.path.exists(doc.file.path):
            raise Http404("File not found")
        mime, _ = mimetypes.guess_type(doc.file.path)
        mime = mime or "application/octet-stream"
        inline = mime in ("application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "text/plain", "text/html")
        resp = FileResponse(open(doc.file.path, "rb"), content_type=mime)
        resp["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{os.path.basename(doc.file.path)}"'
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src data: 'self'; style-src 'unsafe-inline'"
        resp["Cache-Control"] = "private, max-age=300"
        return resp


# =====================================================================
# Doctors directory, working hours & slots
# =====================================================================

class DoctorProfileViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["full_name", "clinic_name", "address", "bio"]
    filterset_fields = {"specialty": ["exact"], "city": ["exact"]}
    ordering_fields = ["full_name", "years_experience", "consultation_fee"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "slots"):
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.user.is_authenticated and is_admin(self.request.user):
            return DoctorAdminSerializer
        return DoctorPublicSerializer

    def get_queryset(self):
        qs = DoctorProfile.objects.select_related("user").prefetch_related("availability", "nurses", "time_off")
        user = self.request.user
        show_all = user.is_authenticated and is_admin(user) and self.request.query_params.get("all") in ("1", "true")
        if not show_all and self.action in ("list", "retrieve", "slots"):
            # hide doctor accounts that are not verified yet; directory-only doctors are always listed
            qs = qs.filter(Q(user__isnull=True) | Q(is_verified=True, user__is_active=True))
        if self.request.query_params.get("bookable") in ("1", "true"):
            qs = qs.filter(user__isnull=False, is_verified=True, accepts_online_booking=True)
        if self.request.query_params.get("verified") in ("0", "false"):
            qs = qs.filter(user__isnull=False, is_verified=False)
        # subscribed doctors first
        return qs.annotate(_sub=Count("user")).order_by("-_sub", "full_name")

    def create(self, request, *args, **kwargs):
        _require(is_admin(request.user), "للمشرف فقط.")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _require(is_admin(request.user), "للمشرف فقط.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _require(is_admin(request.user), "للمشرف فقط.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def slots(self, request, pk=None):
        doctor = self.get_object()
        start = parse_date(request.query_params.get("from") or "") or timezone.localdate()
        days = int(request.query_params.get("days") or 7)
        return Response({"doctor": doctor.id, "can_book": doctor.can_book,
                         "requires_approval": doctor.requires_approval, "slot_minutes": doctor.slot_minutes,
                         "days": scheduling.range_slots(doctor, start, days) if doctor.can_book else []})

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        _require(is_admin(request.user))
        doctor = get_object_or_404(DoctorProfile, pk=pk)
        doctor.is_verified = str(request.data.get("verified", True)).lower() in ("1", "true", "yes")
        doctor.save(update_fields=["is_verified"])
        if doctor.user_id:
            from django.contrib.auth.models import Group
            group = Group.objects.get_or_create(name="Doctor")[0]
            if doctor.is_verified:
                doctor.user.groups.add(group)
                doctor.user.is_staff = True
            else:
                doctor.user.groups.remove(group)
            doctor.user.save(update_fields=["is_staff"])
        if doctor.user_id and doctor.is_verified:
            notify(doctor.user, "تم توثيق حسابك ✅",
                   "يمكنك الآن استقبال حجوزات المرضى. حدّد أوقات دوامك من صفحة الإعدادات.",
                   "DOCTOR_VERIFICATION", "/staff/availability.html")
        _audit(request, "UPDATE", "DoctorProfile", doctor.id, f"verified={doctor.is_verified}")
        return Response(DoctorAdminSerializer(doctor).data)

    def _my_profile(self, request):
        _require(role_of(request.user) == "Doctor", "للأطباء فقط.")
        prof = DoctorProfile.objects.filter(user=request.user).first()
        if not prof:
            prof = DoctorProfile.objects.create(user=request.user, full_name=request.user.get_full_name() or request.user.username)
        return prof

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        prof = self._my_profile(request)
        if request.method == "PATCH":
            ser = DoctorSelfSerializer(prof, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
        return Response(DoctorSelfSerializer(prof).data)

    @action(detail=False, methods=["put"], url_path="me/availability")
    def set_availability(self, request):
        """Replace the weekly schedule: [{"weekday":6,"start_time":"09:00","end_time":"14:00"}, ...]"""
        prof = self._my_profile(request)
        ser = AvailabilitySerializer(data=request.data, many=True)
        ser.is_valid(raise_exception=True)
        rows = sorted(ser.validated_data, key=lambda r: (r["weekday"], r["start_time"]))
        for a, b in zip(rows, rows[1:]):
            if a["weekday"] == b["weekday"] and b["start_time"] < a["end_time"]:
                raise ValidationError({"detail": "يوجد تداخل بين فترتين في نفس اليوم."})
        DoctorAvailability.objects.filter(doctor=prof).delete()
        DoctorAvailability.objects.bulk_create([DoctorAvailability(doctor=prof, **r) for r in rows])
        return Response(AvailabilitySerializer(prof.availability.all(), many=True).data)

    @action(detail=False, methods=["get", "post"], url_path="me/time-off")
    def time_off(self, request):
        prof = self._my_profile(request)
        if request.method == "POST":
            ser = TimeOffSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            DoctorTimeOff.objects.update_or_create(doctor=prof, date=ser.validated_data["date"],
                                                   defaults={"reason": ser.validated_data.get("reason", "")})
        return Response(TimeOffSerializer(prof.time_off.filter(date__gte=timezone.localdate()), many=True).data)

    @action(detail=False, methods=["delete"], url_path=r"me/time-off/(?P<off_id>\d+)")
    def delete_time_off(self, request, off_id=None):
        prof = self._my_profile(request)
        DoctorTimeOff.objects.filter(doctor=prof, id=off_id).delete()
        return Response(status=204)

    @action(detail=False, methods=["get"], url_path="assisted")
    def assisted(self, request):
        """Doctors a nurse works with (or the doctor themself)."""
        qs = DoctorProfile.objects.filter(user__in=doctor_users_for(request.user)).prefetch_related("availability")
        return Response(DoctorPublicSerializer(qs, many=True).data)

# =====================================================================
# Appointments
# =====================================================================

class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reason", "location", "patient__name", "patient__medical_id"]
    ordering_fields = ["start_at", "status", "created_at"]
    filterset_fields = {
        "start_at": ["date", "date__gte", "date__lte", "gte", "lt"],
        "status": ["exact", "in"],
        "practitioner": ["exact"],
        "patient": ["exact"],
        "doctor": ["exact"],
    }

    def get_queryset(self):
        qs = Appointment.objects.select_related("patient", "practitioner", "doctor", "decided_by", "triage")
        qs = appointments_visible_to(self.request.user, qs)
        when = self.request.query_params.get("when")
        now = timezone.now()
        if when == "upcoming":
            qs = qs.filter(start_at__gte=now).order_by("start_at")
        elif when == "past":
            qs = qs.filter(start_at__lt=now).order_by("-start_at")
        else:
            qs = qs.order_by("-start_at")
        return qs

    def get_object(self):
        obj = super().get_object()
        return obj

    def perform_create(self, serializer):
        """Direct creation by staff (e.g. walk-in / phone booking) -> confirmed immediately."""
        user = self.request.user
        _require(in_roles(user, STAFF), "استخدم صفحة الحجز لحجز موعد.")
        practitioner = serializer.validated_data.get("practitioner")
        if practitioner is None and role_of(user) == "Doctor":
            practitioner = user
        if practitioner is None:
            raise ValidationError({"practitioner": "اختر الطبيب."})
        start, end = serializer.validated_data["start_at"], serializer.validated_data["end_at"]
        clash = Appointment.objects.filter(practitioner=practitioner, status__in=Appointment.ACTIVE_STATUSES,
                                           start_at__lt=end, end_at__gt=start).first()
        if clash:
            raise ValidationError({"start_at": f"تعارض مع موعد {clash.patient.name} ({timezone.localtime(clash.start_at):%H:%M})"})
        appt = serializer.save(practitioner=practitioner, status=Appointment.CONFIRMED, booked_by=user, decided_by=user,
                               decided_at=timezone.now())
        if appt.patient.user_id:
            notify(appt.patient.user, "تم حجز موعد لك",
                   f"موعد بتاريخ {timezone.localtime(appt.start_at):%Y-%m-%d %H:%M}", "APPOINTMENT_CONFIRMED",
                   "/patient/appointments.html")

    def perform_update(self, serializer):
        appt = serializer.instance
        _require(can_manage_appointment(self.request.user, appt), "لا تملك صلاحية تعديل هذا الموعد.")
        moved = "start_at" in serializer.validated_data and serializer.validated_data["start_at"] != appt.start_at
        appt = serializer.save()
        if moved and appt.patient.user_id:
            notify(appt.patient.user, "تم تعديل موعدك",
                   f"الموعد الجديد: {timezone.localtime(appt.start_at):%Y-%m-%d %H:%M}", "APPOINTMENT_CONFIRMED",
                   "/patient/appointments.html")

    def destroy(self, request, *args, **kwargs):
        _require(in_roles(request.user, ("Admin", "Nurse")), "حذف المواعيد مسموح للإدمن أو الممرضة فقط.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    def book(self, request):
        ser = BookingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        role = role_of(request.user)
        if role == "Patient":
            patient = patient_of(request.user)
            _require(patient is not None, "لا يوجد سجل مريض مرتبط بحسابك.")
        else:
            _require(role in ("Admin", "Nurse", "Doctor"), "غير مسموح")
            patient = d.get("patient")
            if patient is None:
                raise ValidationError({"patient": "اختر المريض."})
        triage = d.get("triage")
        if triage and triage.patient_id != patient.id:
            triage = None
        appt = _scheduling_call(scheduling.book, doctor=d["doctor"], patient=patient, start_at=d["start_at"],
                                booked_by=request.user, reason=d.get("reason", ""), triage=triage)
        return Response(AppointmentSerializer(appt).data, status=201)

    def _managed(self, pk):
        appt = get_object_or_404(self.get_queryset(), pk=pk)
        _require(can_manage_appointment(self.request.user, appt), "هذا الإجراء للطبيب أو الممرض المسؤول.")
        return appt

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        appt = _scheduling_call(scheduling.approve, self._managed(pk), request.user, request.data.get("note", ""))
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        appt = _scheduling_call(scheduling.reject, self._managed(pk), request.user, request.data.get("note", ""))
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        appt = _scheduling_call(scheduling.set_outcome, self._managed(pk), request.user, Appointment.COMPLETED)
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        appt = _scheduling_call(scheduling.set_outcome, self._managed(pk), request.user, Appointment.NO_SHOW)
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        appt = get_object_or_404(self.get_queryset(), pk=pk)
        by_patient = role_of(request.user) == "Patient"
        if not by_patient:
            _require(can_manage_appointment(request.user, appt))
        appt = _scheduling_call(scheduling.cancel, appt, request.user, by_patient, request.data.get("note", ""))
        return Response(AppointmentSerializer(appt).data)

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """Lightweight events for FullCalendar: ?start=ISO&end=ISO"""
        qs = self.get_queryset()
        start = parse_datetime(request.query_params.get("start") or "") or timezone.now() - dt.timedelta(days=31)
        end = parse_datetime(request.query_params.get("end") or "") or timezone.now() + dt.timedelta(days=62)
        qs = qs.filter(start_at__lt=end, end_at__gt=start).exclude(status__in=[Appointment.REJECTED, Appointment.CANCELLED])
        doctor = request.query_params.get("doctor")
        if doctor:
            qs = qs.filter(doctor_id=doctor)
        events = [{
            "id": a.id, "title": a.patient.name if role_of(request.user) != "Patient" else (a.doctor.full_name if a.doctor_id else "موعد"),
            "start": a.start_at.isoformat(), "end": a.end_at.isoformat(), "status": a.status,
            "reason": a.reason or "", "doctor": a.doctor.full_name if a.doctor_id else "",
            "patient_id": a.patient_id, "medical_id": a.patient.medical_id,
        } for a in qs[:1000]]
        return Response(events)

# =====================================================================
# Notifications & Web Push
# =====================================================================

class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        latest = Notification.objects.filter(user=request.user).values_list("id", flat=True).first()
        return Response({"count": Notification.objects.filter(user=request.user, is_read=False).count(),
                         "latest_id": latest or 0})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        Notification.objects.filter(user=request.user, pk=pk).update(is_read=True)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response(status=204)


class PushPublicKeyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            return Response({"public_key": vapid_keys()[1]})
        except Exception as exc:
            return Response({"public_key": None, "detail": str(exc)}, status=503)


class PushSubscribeView(APIView):
    def post(self, request):
        sub = request.data.get("subscription") or request.data
        keys = sub.get("keys") or {}
        if not sub.get("endpoint") or not keys.get("p256dh") or not keys.get("auth"):
            raise ValidationError({"detail": "invalid subscription"})
        PushSubscription.objects.update_or_create(
            endpoint=sub["endpoint"][:500],
            defaults={"user": request.user, "p256dh": keys["p256dh"], "auth": keys["auth"]})
        return Response({"ok": True}, status=201)

    def delete(self, request):
        PushSubscription.objects.filter(user=request.user, endpoint=(request.data.get("endpoint") or "")[:500]).delete()
        return Response(status=204)

# =====================================================================
# AI: triage guide, doctor assistant, health chat
# =====================================================================

class TriageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = TriageSessionSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get_queryset(self):
        qs = TriageSession.objects.filter(patient__in=accessible_patients(self.request.user))
        pid = self.request.query_params.get("patient")
        if pid:
            qs = qs.filter(patient_id=pid)
        return qs

    def get_throttles(self):
        return super().get_throttles() if self.action in ("create", "reply") else []

    def create(self, request):
        patient = patient_of(request.user)
        _require(patient is not None, "الدليل الصحي متاح للمرضى.")
        msg = (request.data.get("message") or "").strip()
        if len(msg) < 3:
            raise ValidationError({"message": "صف حالتك ببضع كلمات."})
        session = TriageSession.objects.create(patient=patient, engine="auto")
        session = ai.triage_step(session, patient, msg)
        return Response(TriageSessionSerializer(session).data, status=201)

    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        session = get_object_or_404(TriageSession, pk=pk, patient__user=request.user)
        if session.status != TriageSession.ACTIVE:
            raise ValidationError({"detail": "انتهت هذه الجلسة، ابدأ جلسة جديدة."})
        msg = (request.data.get("message") or "").strip()
        if not msg:
            raise ValidationError({"message": "اكتب إجابتك."})
        session = ai.triage_step(session, session.patient, msg)
        return Response(TriageSessionSerializer(session).data)


class DoctorAssistView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def post(self, request):
        _require(role_of(request.user) in ("Doctor", "Nurse", "Admin"), "للكادر الطبي فقط.")
        patient = get_object_or_404(Patient, pk=request.data.get("patient"))
        _require(can_view_patient(request.user, patient), "لا تملك صلاحية الاطلاع على هذا المريض.")
        question = (request.data.get("question") or "").strip() or "لخّص حالة المريض واقترح خطة تقييم."
        last = TriageSession.objects.filter(patient=patient, status=TriageSession.COMPLETED).first()
        return Response(ai.doctor_assist(patient, question, last.result if last else None))


class ChatWithPatientView(APIView):
    """Free health Q&A for the patient (non-diagnostic), stored as chat history."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def post(self, request):
        patient = patient_of(request.user)
        _require(patient is not None, "للمرضى فقط.")
        message = (request.data.get("message") or "").strip()[:2000]
        if not message:
            raise ValidationError({"message": "اكتب سؤالك."})
        history = list(ChatMessage.objects.filter(patient=patient).order_by("-created_at")[:6])[::-1]
        answer, engine = None, "rules"
        if ai.ai_available():
            try:
                import json as _json
                import re
                msgs = [{"role": "system", "content": (
                    "أنت مساعد صحي غير تشخيصي في تطبيق الهوية الطبية الذكية. أجب بالعربية بفقرات قصيرة ونقاط تبدأ بـ •، "
                    "بدون رموز * أو #، ولا تذكر جرعات أدوية، وانبّه لعلامات الخطر. السجل الطبي للمريض:\n"
                    + _json.dumps(ai.record_snapshot(patient), ensure_ascii=False, default=str))}]
                msgs += [{"role": "user" if m.role == "USER" else "assistant", "content": m.message} for m in history]
                msgs.append({"role": "user", "content": message})
                resp = ai.chat_generic({"messages": msgs, "temperature": 0.3, "num_predict": 800}, timeout=90)
                answer = re.sub(r"<think>.*?</think>", "", (resp.get("message") or {}).get("content", ""), flags=re.S).strip()
                engine = "ollama"
            except Exception:
                answer = None
        if not answer:
            answer = ("المساعد الذكي غير متاح حالياً. لتحديد الاختصاص المناسب لحالتك استخدم \"الدليل الصحي\"، "
                      "وفي الحالات الطارئة توجّه إلى الإسعاف فوراً.")
        ChatMessage.objects.bulk_create([
            ChatMessage(patient=patient, role="USER", message=message),
            ChatMessage(patient=patient, role="ASSISTANT", message=answer, metadata={"engine": engine}),
        ])
        return Response({"user_message": message, "assistant_message": answer, "engine": engine})


class ChatHistoryView(APIView):
    def get(self, request):
        patient = patient_of(request.user)
        if not patient:
            return Response({"messages": []})
        msgs = ChatMessage.objects.filter(patient=patient).order_by("-created_at")[:100]
        return Response({"messages": ChatMessageSerializer(reversed(list(msgs)), many=True).data})


class AIStatusView(APIView):
    def get(self, request):
        key = "ai_status"
        val = cache.get(key)
        if val is None:
            val = ai.ai_available()
            cache.set(key, val, 30)
        return Response({"llm_available": val})

# =====================================================================
# Dictionaries
# =====================================================================

class _DictionaryViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name"]
    ordering = ["code"]

    def get_permissions(self):
        return [IsAuthenticated()]

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            _require(is_admin(request.user), "للمشرف فقط.")


class ConditionDictionaryViewSet(_DictionaryViewSet):
    queryset = ConditionDictionary.objects.all().order_by("code")
    serializer_class = ConditionDictionarySerializer


class ObservationDictionaryViewSet(_DictionaryViewSet):
    queryset = ObservationDictionary.objects.all().order_by("code")
    serializer_class = ObservationDictionarySerializer


class MedicationDictionaryViewSet(_DictionaryViewSet):
    queryset = MedicationDictionary.objects.all().order_by("code")
    serializer_class = MedicationDictionarySerializer

# =====================================================================
# Administration
# =====================================================================

class UserAdminViewSet(viewsets.ModelViewSet):
    serializer_class = UserAdminSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username", "date_joined", "last_login"]
    filterset_fields = {"is_active": ["exact"]}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _require(is_admin(request.user), "للمشرف فقط.")

    def get_queryset(self):
        qs = User.objects.prefetch_related("groups").select_related("doctor_profile").order_by("-id")
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(groups__name=role)
        return qs

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        _require(user.id != request.user.id, "لا يمكنك حذف حسابك.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="change-password")
    def change_password(self, request, pk=None):
        user = self.get_object()
        new = request.data.get("new_password") or ""
        if len(new) < 8:
            raise ValidationError({"new_password": "8 أحرف على الأقل."})
        user.set_password(new)
        user.save(update_fields=["password"])
        _audit(request, "UPDATE", "User", user.id, "password changed by admin")
        return Response({"detail": "تم تغيير كلمة المرور."})

    @action(detail=True, methods=["post"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        user = self.get_object()
        _require(user.id != request.user.id, "لا يمكنك تعطيل حسابك.")
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        _audit(request, "UPDATE", "User", user.id, f"is_active={user.is_active}")
        return Response({"is_active": user.is_active})


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEventSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["actor__username", "resource", "action", "resource_id"]
    filterset_fields = {"action": ["exact"], "resource": ["exact"], "created_at": ["date__gte", "date__lte"]}

    def get_queryset(self):
        _require(is_admin(self.request.user), "للمشرف فقط.")
        return AuditEvent.objects.select_related("actor").order_by("-created_at")


class AdminReportView(APIView):
    def get(self, request):
        _require(is_admin(request.user), "للمشرف فقط.")
        dfrom = parse_date(request.query_params.get("date_from") or "")
        dto = parse_date(request.query_params.get("date_to") or "")
        trunc = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}.get(request.query_params.get("group_by", "day"), TruncDay)
        appt = Appointment.objects.all()
        if dfrom:
            appt = appt.filter(start_at__date__gte=dfrom)
        if dto:
            appt = appt.filter(start_at__date__lte=dto)
        series = appt.annotate(p=trunc("start_at")).values("p").annotate(count=Count("id")).order_by("p")
        return Response({
            "appointments": appt.count(),
            "appointments_by_status": list(appt.values("status").annotate(count=Count("id"))),
            "appointments_over_time": [{"period": s["p"].date().isoformat(), "count": s["count"]} for s in series if s["p"]],
            "triage_by_specialty": list(TriageSession.objects.filter(status="COMPLETED")
                                        .values("result__specialty").annotate(count=Count("id")).order_by("-count")[:10]),
        })
