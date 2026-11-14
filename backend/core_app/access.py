"""Role-based access rules used by the API views."""
from django.contrib.auth.models import User

from .models import DoctorProfile, Patient

ROLES = ("Admin", "Doctor", "Nurse", "Patient")
STAFF = ("Admin", "Doctor", "Nurse")
PATIENT_EDITABLE_FIELDS = ("phone", "email", "address")


def role_of(user):
    """Primary role of a user, cached on the user object for the duration of the request."""
    if not user or not user.is_authenticated:
        return None
    cached = getattr(user, "_smi_role", None)
    if cached is not None:
        return cached
    if user.is_superuser:
        role = "Admin"
    else:
        names = set(user.groups.values_list("name", flat=True))
        role = next((r for r in ROLES if r in names), "")
    user._smi_role = role
    return role


def in_roles(user, roles):
    return role_of(user) in roles


def is_admin(user):
    return role_of(user) == "Admin"


def is_staff_role(user):
    return role_of(user) in STAFF


def patient_of(user):
    """Patient record linked to a Patient user (cached)."""
    if not user or not user.is_authenticated:
        return None
    if not hasattr(user, "_smi_patient"):
        user._smi_patient = Patient.objects.filter(user=user, is_active=True).first()
    return user._smi_patient


def accessible_patients(user):
    role = role_of(user)
    if role in STAFF:
        return Patient.objects.all()
    if role == "Patient":
        return Patient.objects.filter(user=user)
    return Patient.objects.none()


def can_view_patient(user, patient):
    if patient is None:
        return False
    if is_staff_role(user):
        return True
    return role_of(user) == "Patient" and patient.user_id == user.id


def can_write_records(user):
    """Medical records are written by medical staff."""
    return is_staff_role(user)


def can_manage_appointment(user, appointment):
    """Approve, reject, complete or reschedule: medical staff."""
    return is_staff_role(user)


def appointments_visible_to(user, qs):
    role = role_of(user)
    if role in STAFF:
        return qs
    if role == "Patient":
        return qs.filter(patient__user=user)
    return qs.none()


def doctor_users_for(user):
    """Doctor accounts a staff member works for: a doctor -> themself, a nurse -> assigned doctors."""
    role = role_of(user)
    if role == "Doctor":
        return User.objects.filter(pk=user.pk)
    if role == "Nurse":
        return User.objects.filter(doctor_profile__nurses=user)
    return User.objects.none()


def booking_staff(doctor: DoctorProfile):
    """Who gets notified about a booking request: the doctor + assigned nurses (all nurses if none assigned)."""
    users = [doctor.user] if doctor.user_id else []
    nurses = list(doctor.nurses.filter(is_active=True))
    if not nurses:
        nurses = list(User.objects.filter(groups__name="Nurse", is_active=True))
    return users + nurses
