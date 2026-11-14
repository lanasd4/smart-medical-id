"""Slot generation and booking workflow (book, approve, reject, cancel, complete)."""
import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone

from .access import booking_staff
from .models import Appointment, DoctorProfile
from .notify import notify

MIN_LEAD_MINUTES = 15  # a slot must start at least this far in the future


class BookingError(Exception):
    def __init__(self, message, code="booking_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _aware(date, time):
    return timezone.make_aware(dt.datetime.combine(date, time), timezone.get_current_timezone())


def _day_bounds(date):
    start = _aware(date, dt.time.min)
    return start, start + dt.timedelta(days=1)


def day_slots(doctor: DoctorProfile, date: dt.date, taken=None, now=None):
    """All slots of a day with availability flag. `taken` = set of busy (start,end) tuples (optional prefetch)."""
    now = now or timezone.now()
    if date < timezone.localdate(now) or date > timezone.localdate(now) + dt.timedelta(days=doctor.booking_window_days):
        return []
    rules = [r for r in doctor.availability.all() if r.weekday == date.weekday()]
    if not rules or any(t.date == date for t in doctor.time_off.all()):
        return []
    if taken is None:
        day_start, day_end = _day_bounds(date)
        taken = list(
            Appointment.objects.filter(
                practitioner_id=doctor.user_id, status__in=Appointment.ACTIVE_STATUSES,
                start_at__lt=day_end, end_at__gt=day_start,
            ).values_list("start_at", "end_at")
        )
    length = dt.timedelta(minutes=doctor.slot_minutes)
    earliest = now + dt.timedelta(minutes=MIN_LEAD_MINUTES)
    slots = []
    for rule in rules:
        cur = _aware(date, rule.start_time)
        end = _aware(date, rule.end_time)
        while cur + length <= end:
            s_end = cur + length
            busy = any(b_start < s_end and b_end > cur for b_start, b_end in taken)
            slots.append({
                "start": cur.isoformat(),
                "end": s_end.isoformat(),
                "available": (not busy) and cur >= earliest,
            })
            cur = s_end
    return slots


def range_slots(doctor: DoctorProfile, start_date: dt.date, days: int = 7):
    """Slots for several consecutive days with a single query for the busy times."""
    days = max(1, min(days, 31))
    range_start, _ = _day_bounds(start_date)
    range_end = range_start + dt.timedelta(days=days)
    taken = list(
        Appointment.objects.filter(
            practitioner_id=doctor.user_id, status__in=Appointment.ACTIVE_STATUSES,
            start_at__lt=range_end, end_at__gt=range_start,
        ).values_list("start_at", "end_at")
    )
    now = timezone.now()
    out = []
    for i in range(days):
        d = start_date + dt.timedelta(days=i)
        slots = day_slots(doctor, d, taken=taken, now=now)
        out.append({
            "date": d.isoformat(),
            "weekday": d.weekday(),
            "slots": slots,
            "available_count": sum(1 for s in slots if s["available"]),
        })
    return out


def book(*, doctor: DoctorProfile, patient, start_at: dt.datetime, booked_by, reason="", triage=None):
    if not doctor.can_book:
        raise BookingError("هذا الطبيب غير مشترك بالحجز الإلكتروني. يمكنك التواصل معه عبر الهاتف.", "not_bookable")
    if timezone.is_naive(start_at):
        start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
    local_date = timezone.localtime(start_at).date()
    valid = {s["start"]: s for s in day_slots(doctor, local_date)}
    slot = valid.get(timezone.localtime(start_at).isoformat())
    if slot is None:
        raise BookingError("الوقت المختار ليس ضمن مواعيد دوام الطبيب.", "invalid_slot")
    if not slot["available"]:
        raise BookingError("هذا الموعد محجوز أو انتهى وقته، اختر موعداً آخر.", "slot_taken")
    if Appointment.objects.filter(patient=patient, practitioner=doctor.user,
                                  status__in=Appointment.ACTIVE_STATUSES, start_at__gte=timezone.now()).count() >= 3:
        raise BookingError("لديك 3 مواعيد قادمة مع هذا الطبيب بالفعل.", "too_many")

    status = Appointment.PENDING if doctor.requires_approval else Appointment.CONFIRMED
    try:
        with transaction.atomic():
            appt = Appointment.objects.create(
                patient=patient, practitioner=doctor.user, doctor=doctor,
                start_at=start_at, end_at=start_at + dt.timedelta(minutes=doctor.slot_minutes),
                reason=(reason or "")[:255], location=doctor.clinic_name or doctor.address or None,
                status=status, triage=triage, booked_by=booked_by,
                decided_at=timezone.now() if status == Appointment.CONFIRMED else None,
            )
    except IntegrityError:
        # another request took this slot a moment ago (DB unique constraint)
        raise BookingError("سبقك مريض آخر لهذا الموعد، اختر موعداً آخر.", "slot_taken")

    when = timezone.localtime(start_at).strftime("%Y-%m-%d %H:%M")
    if status == Appointment.PENDING:
        notify(booking_staff(doctor), "طلب موعد جديد",
               f"{patient.name} طلب موعداً بتاريخ {when}", "APPOINTMENT_REQUEST", "/staff/requests.html")
        if patient.user_id:
            notify(patient.user, "تم إرسال طلب الموعد",
                   f"طلبك مع د. {doctor.full_name} بتاريخ {when} بانتظار الموافقة",
                   "APPOINTMENT_REQUEST", "/patient/appointments.html")
    else:
        notify(booking_staff(doctor), "موعد جديد مؤكد",
               f"{patient.name} حجز موعداً بتاريخ {when}", "APPOINTMENT_CONFIRMED", "/staff/calendar.html")
        if patient.user_id:
            notify(patient.user, "تم تثبيت موعدك",
                   f"موعدك مع د. {doctor.full_name} بتاريخ {when} مؤكد", "APPOINTMENT_CONFIRMED",
                   "/patient/appointments.html")
    return appt


def _patient_user(appt):
    return appt.patient.user if appt.patient_id and appt.patient.user_id else None


def _when(appt):
    return timezone.localtime(appt.start_at).strftime("%Y-%m-%d %H:%M")


def _doctor_name(appt):
    if appt.doctor_id:
        return appt.doctor.full_name
    return appt.practitioner.get_full_name() or appt.practitioner.username if appt.practitioner_id else ""


@transaction.atomic
def approve(appt: Appointment, by_user, note=""):
    if appt.status != Appointment.PENDING:
        raise BookingError("يمكن الموافقة على الطلبات المعلّقة فقط.", "bad_status")
    appt.status = Appointment.CONFIRMED
    appt.decided_by, appt.decided_at, appt.decision_note = by_user, timezone.now(), (note or "")[:255]
    appt.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    notify(_patient_user(appt), "تم تأكيد موعدك ✅",
           f"موعدك مع د. {_doctor_name(appt)} بتاريخ {_when(appt)} تم تثبيته", "APPOINTMENT_CONFIRMED",
           "/patient/appointments.html")
    return appt


@transaction.atomic
def reject(appt: Appointment, by_user, note=""):
    if appt.status != Appointment.PENDING:
        raise BookingError("يمكن رفض الطلبات المعلّقة فقط.", "bad_status")
    appt.status = Appointment.REJECTED
    appt.decided_by, appt.decided_at, appt.decision_note = by_user, timezone.now(), (note or "")[:255]
    appt.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    msg = f"طلب موعدك مع د. {_doctor_name(appt)} بتاريخ {_when(appt)} لم تتم الموافقة عليه"
    if note:
        msg += f" — {note}"
    notify(_patient_user(appt), "تعذّر تأكيد الموعد", msg, "APPOINTMENT_REJECTED", "/patient/doctors.html")
    return appt


@transaction.atomic
def cancel(appt: Appointment, by_user, by_patient: bool, note=""):
    if appt.status not in Appointment.ACTIVE_STATUSES:
        raise BookingError("لا يمكن إلغاء هذا الموعد.", "bad_status")
    if by_patient and appt.start_at <= timezone.now():
        raise BookingError("لا يمكن إلغاء موعد بدأ أو انتهى.", "past")
    appt.status = Appointment.CANCELLED
    appt.decided_by, appt.decided_at, appt.decision_note = by_user, timezone.now(), (note or "")[:255]
    appt.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    if by_patient:
        staff = booking_staff(appt.doctor) if appt.doctor_id else [appt.practitioner]
        notify(staff, "إلغاء موعد", f"{appt.patient.name} ألغى موعده بتاريخ {_when(appt)}",
               "APPOINTMENT_CANCELLED", "/staff/calendar.html")
    else:
        notify(_patient_user(appt), "تم إلغاء موعدك",
               f"موعدك بتاريخ {_when(appt)} أُلغي من قبل العيادة" + (f" — {note}" if note else ""),
               "APPOINTMENT_CANCELLED", "/patient/appointments.html")
    return appt


@transaction.atomic
def set_outcome(appt: Appointment, by_user, outcome):
    if outcome not in (Appointment.COMPLETED, Appointment.NO_SHOW):
        raise BookingError("حالة غير صالحة.", "bad_status")
    if appt.status != Appointment.CONFIRMED:
        raise BookingError("يمكن إنهاء المواعيد المؤكدة فقط.", "bad_status")
    appt.status = outcome
    appt.decided_by, appt.decided_at = by_user, timezone.now()
    appt.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return appt
