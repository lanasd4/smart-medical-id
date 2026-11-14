# -*- coding: utf-8 -*-
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core_app import views as v

router = DefaultRouter()
router.register(r"patients", v.PatientViewSet, basename="patients")
router.register(r"appointments", v.AppointmentViewSet, basename="appointments")
router.register(r"doctors", v.DoctorProfileViewSet, basename="doctors")
router.register(r"encounters", v.EncounterViewSet, basename="encounters")
router.register(r"observations", v.ObservationViewSet, basename="observations")
router.register(r"medications", v.MedicationViewSet, basename="medications")
router.register(r"conditions", v.ConditionViewSet, basename="conditions")
router.register(r"allergies", v.AllergyViewSet, basename="allergies")
router.register(r"procedures", v.ProcedureViewSet, basename="procedures")
router.register(r"documents", v.DocumentRefViewSet, basename="documents")
router.register(r"consents", v.ConsentViewSet, basename="consents")
router.register(r"notifications", v.NotificationViewSet, basename="notifications")
router.register(r"ai/triage", v.TriageViewSet, basename="triage")
router.register(r"dictionaries/conditions", v.ConditionDictionaryViewSet, basename="dict-conditions")
router.register(r"dictionaries/observations", v.ObservationDictionaryViewSet, basename="dict-observations")
router.register(r"dictionaries/medications", v.MedicationDictionaryViewSet, basename="dict-medications")
router.register(r"users", v.UserAdminViewSet, basename="users")
router.register(r"admin/audit-events", v.AuditEventViewSet, basename="admin-audit-events")

urlpatterns = [
    path("django-admin/", admin.site.urls),

    # Auth & identity
    path("api/token/", v.SmartTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/register/", v.RegisterView.as_view(), name="register"),
    path("api/whoami/", v.WhoAmIView.as_view(), name="whoami"),
    path("api/me/", v.MeView.as_view(), name="me"),
    path("api/me/password/", v.ChangeOwnPasswordView.as_view(), name="change-own-password"),
    path("api/meta/", v.MetaView.as_view(), name="meta"),
    path("api/dashboard/", v.DashboardView.as_view(), name="dashboard"),

    # Documents (served through an access check, never as public media)
    path("api/documents/<int:doc_id>/view/", v.ServeDocumentView.as_view(), name="document-view"),

    # Web push (PWA)
    path("api/push/public-key/", v.PushPublicKeyView.as_view(), name="push-public-key"),
    path("api/push/subscribe/", v.PushSubscribeView.as_view(), name="push-subscribe"),

    # AI
    path("api/ai/status/", v.AIStatusView.as_view(), name="ai-status"),
    path("api/ai/doctor-assist/", v.DoctorAssistView.as_view(), name="ai-doctor-assist"),
    path("api/ai/chat/", v.ChatWithPatientView.as_view(), name="ai-chat"),
    path("api/ai/chat/history/", v.ChatHistoryView.as_view(), name="ai-chat-history"),

    path("api/admin/reports/summary/", v.AdminReportView.as_view(), name="admin-report"),
    path("api/", include(router.urls)),
]
