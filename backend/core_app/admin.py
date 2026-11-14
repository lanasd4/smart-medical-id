from django.contrib import admin
from .models import (
    Patient, PatientIdentifier, Condition, Allergy, Medication,
    Observation, Encounter, DocumentRef, Immunization, Consent,
    AuditEvent, Appointment, LoginSession,
    ConditionDictionary, ObservationDictionary, MedicationDictionary,
    ChatMessage
)


class PatientIdentifierInline(admin.TabularInline):
    model = PatientIdentifier
    extra = 1


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "date_of_birth", "gender", "phone", "email", "user", "blood_type")
    search_fields = ("name", "phone", "email")
    list_filter = ("gender",)
    inlines = [PatientIdentifierInline]


@admin.register(PatientIdentifier)
class PatientIdentifierAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "type", "value", "is_primary")
    search_fields = ("value",)
    list_filter = ("type", "is_primary")


# ------------------------------------------------------------------
# Reference Dictionaries
# ------------------------------------------------------------------

@admin.register(ConditionDictionary)
class ConditionDictionaryAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(ObservationDictionary)
class ObservationDictionaryAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(MedicationDictionary)
class MedicationDictionaryAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


# ------------------------------------------------------------------
# Medical Records
# ------------------------------------------------------------------

@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "code", "status", "onset_date")
    search_fields = ("code__code", "code__name")
    list_filter = ("status",)


@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "substance", "reaction", "severity", "recorded_date")
    search_fields = ("substance", "reaction")
    list_filter = ("severity",)


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "code", "local_name", "dose", "frequency", "start_date", "end_date", "status")
    search_fields = ("code__code", "code__name", "local_name")
    list_filter = ("status",)


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "code", "value", "unit", "observed_at")
    search_fields = ("code__code", "code__name", "value")
    list_filter = ("code",)


class ObservationInline(admin.TabularInline):
    model = Observation
    extra = 1


class MedicationInline(admin.TabularInline):
    model = Medication
    extra = 1


class DocumentRefInline(admin.TabularInline):
    model = DocumentRef
    extra = 1


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "start_at", "end_at", "type", "reason")
    search_fields = ("reason",)
    list_filter = ("type",)
    inlines = [ObservationInline, MedicationInline, DocumentRefInline]


@admin.register(DocumentRef)
class DocumentRefAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "doc_type", "title", "uploaded_at")
    search_fields = ("title",)
    list_filter = ("doc_type",)


@admin.register(Immunization)
class ImmunizationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "vaccine_name", "administered_at", "lot_number", "performer")
    search_fields = ("vaccine_name", "lot_number")
    list_filter = ("vaccine_name",)


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "status", "valid_from", "valid_to", "purpose")
    list_filter = ("status",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "actor", "action", "resource", "resource_id", "ip", "created_at")
    search_fields = ("actor__username", "resource", "resource_id")
    list_filter = ("action", "resource")
    readonly_fields = ("actor", "action", "resource", "resource_id", "metadata", "ip", "created_at") 


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "ip_address", "login_at", "logout_at", "is_active")
    search_fields = ("user__username", "session_key", "ip_address", "user_agent")
    list_filter = ("is_active",)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "practitioner", "start_at", "end_at", "status", "location")
    list_filter = ("status", "location")
    search_fields = ("patient__name", "practitioner__username", "reason")
    ordering = ("-start_at",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "role", "message_preview", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("patient__name", "message")
    readonly_fields = ("patient", "role", "message", "metadata", "created_at")
    ordering = ("-created_at",)
    
    def message_preview(self, obj):
        """Show first 50 characters of message"""
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = "Message Preview"


# ------------------------------------------------------------------
# Smart Medical ID additions
# ------------------------------------------------------------------
from .models import DoctorProfile, DoctorAvailability, DoctorTimeOff, Procedure, Notification, TriageSession


class DoctorAvailabilityInline(admin.TabularInline):
    model = DoctorAvailability
    extra = 0


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "specialty", "city", "user", "is_verified", "requires_approval")
    list_filter = ("specialty", "city", "is_verified")
    search_fields = ("full_name", "clinic_name")
    filter_horizontal = ("nurses",)
    inlines = [DoctorAvailabilityInline]


admin.site.register(DoctorTimeOff)
admin.site.register(Procedure)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read")


@admin.register(TriageSession)
class TriageSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "status", "engine", "created_at")
    list_filter = ("status", "engine")
