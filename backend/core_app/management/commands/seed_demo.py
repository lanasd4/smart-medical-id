"""Demo data: doctors directory, demo accounts and an optional set of load-test patients."""
import datetime as dt
import random

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from core_app.models import (
    Allergy, Condition, DoctorAvailability, DoctorProfile, Medication, Patient, Procedure,
)

DEMO_PASSWORD = "Strong@123"  # test-only accounts for local demos — never use in production

DIRECTORY = [
    # name, specialty, city, clinic, phone, years
    ("رامي الخطيب", "CARDIOLOGY", "دمشق", "مركز القلب التخصصي — المالكي", "011-000-0001", 18),
    ("ريم السيد", "DERMATOLOGY", "دمشق", "عيادة البشرة — أبو رمانة", "011-000-0002", 9),
    ("مازن العلي", "ORTHOPEDICS", "حلب", "مشفى الرازي", "021-000-0003", 22),
    ("هالة درويش", "PEDIATRICS", "حمص", "عيادة الطفولة السعيدة", "031-000-0004", 12),
    ("وسيم حداد", "ENT", "اللاذقية", "عيادة الأذن والأنف والحنجرة", "041-000-0005", 15),
    ("نور الهدى قاسم", "OBGYN", "دمشق", "مركز الأمومة — المزة", "011-000-0006", 11),
    ("فادي منصور", "NEUROLOGY", "حماة", "عيادة الأعصاب", "033-000-0007", 20),
    ("لمى عيسى", "OPHTHALMOLOGY", "طرطوس", "مركز العيون", "043-000-0008", 8),
    ("باسل يوسف", "GASTRO", "دمشق", "عيادة الهضمية — الشعلان", "011-000-0009", 16),
    ("سلمى عباس", "ENDOCRINOLOGY", "حلب", "مركز السكري والغدد", "021-000-0010", 13),
    ("خالد الأحمد", "PULMONOLOGY", "درعا", "عيادة الصدرية", "015-000-0011", 19),
    ("دانة شحادة", "PSYCHIATRY", "دمشق", "عيادة الصحة النفسية", "011-000-0012", 7),
    ("طارق حمدان", "UROLOGY", "السويداء", "عيادة المسالك البولية", "016-000-0013", 14),
    ("رنا موسى", "DENTISTRY", "اللاذقية", "مركز ابتسامة لطب الأسنان", "041-000-0014", 6),
    ("عمر الحلبي", "GENERAL_SURGERY", "حمص", "مشفى الحكمة", "031-000-0015", 25),
    ("جود سليمان", "RHEUMATOLOGY", "دمشق", "عيادة المفاصل", "011-000-0016", 10),
    ("مروان زيدان", "NEPHROLOGY", "حلب", "مركز الكلية", "021-000-0017", 17),
    ("سارة نجار", "INTERNAL", "ريف دمشق", "عيادة الداخلية — جرمانا", "011-000-0018", 9),
    ("إياد الشامي", "GENERAL", "دير الزور", "مستوصف الفرات", "051-000-0019", 12),
    ("ليندا خوري", "ONCOLOGY", "دمشق", "مركز الأورام — البيروني", "011-000-0020", 21),
]

DEMO_DOCTORS = {
    # username: (full name, specialty, clinic, requires_approval)
    "dr.samer": ("سامر حسن", "INTERNAL", "عيادة الداخلية — المزة", True),
    "dr_smith": ("جون سميث", "CARDIOLOGY", "مركز القلب — المهاجرين", True),
    "lulu": ("لؤلؤة كرم", "DERMATOLOGY", "عيادة الجلدية — الشعلان", False),
}


class Command(BaseCommand):
    help = "Seed demo directory doctors, demo profiles and (optionally) load-test patients."

    def add_arguments(self, parser):
        parser.add_argument("--load-users", type=int, default=0)

    @transaction.atomic
    def handle(self, *args, **opts):
        rnd = random.Random(7)
        added = 0
        for name, spec, city, clinic, phone, years in DIRECTORY:
            _, created = DoctorProfile.objects.get_or_create(
                full_name=name, user=None,
                defaults=dict(specialty=spec, city=city, clinic_name=clinic, phone=phone, years_experience=years,
                              address=clinic.split("—")[-1].strip(), is_verified=False,
                              bio="طبيب في الدليل الوطني. للحجز يرجى الاتصال بالعيادة."))
            added += created
        self.stdout.write(f"directory doctors added: {added}")

        nurses = list(User.objects.filter(groups__name="Nurse"))
        for username, (full, spec, clinic, approval) in DEMO_DOCTORS.items():
            u = User.objects.filter(username=username).first()
            if not u:
                continue
            u.groups.add(Group.objects.get_or_create(name="Doctor")[0])
            prof, _ = DoctorProfile.objects.get_or_create(user=u, defaults={"full_name": full})
            if prof.full_name in (u.username, "") or prof.specialty == "GENERAL":
                prof.full_name, prof.specialty, prof.clinic_name = full, spec, clinic
                prof.city, prof.address = "دمشق", clinic.split("—")[-1].strip()
                prof.years_experience = rnd.randint(6, 20)
                prof.consultation_fee = rnd.choice([25000, 30000, 40000, 50000])
                prof.bio = "طبيب مشترك في منصة الهوية الطبية الذكية ويستقبل الحجوزات الإلكترونية."
            prof.is_verified, prof.requires_approval, prof.accepts_online_booking = True, approval, True
            prof.save()
            if not prof.availability.exists():
                for wd in (5, 6, 0, 1, 2, 3):  # Sat..Thu
                    DoctorAvailability.objects.create(doctor=prof, weekday=wd, start_time=dt.time(9), end_time=dt.time(13))
                DoctorAvailability.objects.create(doctor=prof, weekday=0, start_time=dt.time(16), end_time=dt.time(19))
            if nurses:
                prof.nurses.add(*nurses)
        self.stdout.write("demo doctor profiles ready")

        p = Patient.objects.filter(user__username="patient.nour").first()
        if p:
            if not p.blood_type:
                p.blood_type, p.date_of_birth, p.gender = "A+", dt.date(1992, 4, 18), "أنثى"
                p.height_cm, p.weight_kg = 165, 62
                p.emergency_contact_name, p.emergency_contact_phone = "أحمد (الزوج)", "0900-000-001"
                p.save()
            if not p.allergies.exists():
                Allergy.objects.create(patient=p, substance="البنسلين", reaction="طفح جلدي وحكة", severity="شديد")
            if not p.conditions.exists():
                Condition.objects.create(patient=p, name="داء السكري من النمط الثاني", is_chronic=True, status="Controlled", onset_date=dt.date(2019, 3, 1))
                Condition.objects.create(patient=p, name="ربو قصبي خفيف", is_chronic=True, status="Active", onset_date=dt.date(2010, 9, 1))
            if not p.medications.exists():
                Medication.objects.create(patient=p, local_name="ميتفورمين", dose="500 ملغ", frequency="مرتين يومياً", status="ACTIVE", start_date=dt.date(2019, 3, 5))
                Medication.objects.create(patient=p, local_name="بخاخ سالبوتامول", dose="عند اللزوم", frequency="عند الضيق", status="ACTIVE", start_date=dt.date(2015, 1, 1))
            if not p.procedures.exists():
                Procedure.objects.create(patient=p, name="استئصال الزائدة الدودية", performed_on=dt.date(2012, 7, 14), hospital="مشفى المواساة")
            self.stdout.write("demo patient record ready")

        # demo accounts (password: DEMO_PASSWORD)
        g = {n: Group.objects.get_or_create(name=n)[0] for n in ("Doctor", "Nurse", "Patient")}
        lina = User.objects.filter(username="nurse.lina").first()
        for uname, first, last, spec, clinic, approval in [
            ("dr.khaled", "خالد", "العمر", "PULMONOLOGY", "عيادة الصدرية — الشعلان", False),
            ("dr.rania", "رانيا", "يوسف", "CARDIOLOGY", "مركز القلب — المالكي", True),
        ]:
            u, created = User.objects.get_or_create(username=uname, defaults={"first_name": first, "last_name": last, "is_staff": True})
            if created:
                u.set_password(DEMO_PASSWORD); u.save()
            u.groups.add(g["Doctor"])
            prof, made = DoctorProfile.objects.get_or_create(user=u, defaults=dict(
                full_name=f"{first} {last}", specialty=spec, city="دمشق", clinic_name=clinic,
                address=clinic.split("—")[-1].strip(), phone="011-000-0021", years_experience=10,
                consultation_fee=35000, is_verified=True, requires_approval=approval,
                bio="حساب تجريبي لتجربة الحجز."))
            if made:
                for wd in (5, 6, 0, 1, 2, 3):
                    DoctorAvailability.objects.create(doctor=prof, weekday=wd, start_time=dt.time(10), end_time=dt.time(14))
            if lina:
                prof.nurses.add(lina)
        for uname, name, blood, dob, gender in [
            ("patient.omar", "عمر الحلبي", "O+", dt.date(1985, 6, 2), "ذكر"),
            ("patient.maya", "مايا سليمان", "B-", dt.date(2000, 1, 20), "أنثى"),
        ]:
            u, created = User.objects.get_or_create(username=uname)
            if created:
                u.set_password(DEMO_PASSWORD); u.save()
            u.groups.add(g["Patient"])
            Patient.objects.get_or_create(user=u, defaults=dict(name=name, blood_type=blood, date_of_birth=dob, gender=gender,
                                                                 phone="0900-000-002"))
        u, created = User.objects.get_or_create(username="nurse.huda", defaults={"first_name": "هدى", "last_name": "الخطيب", "is_staff": True})
        if created:
            u.set_password(DEMO_PASSWORD); u.save()
        u.groups.add(g["Nurse"])
        self.stdout.write("demo accounts ready (see docs/demo-accounts.md)")

        n = opts["load_users"]
        if n:
            group = Group.objects.get_or_create(name="Patient")[0]
            made = 0
            for i in range(1, n + 1):
                uname = f"loadpatient{i}"
                if User.objects.filter(username=uname).exists():
                    continue
                u = User.objects.create_user(uname, password="LoadTest#2026")
                u.groups.add(group)
                Patient.objects.create(user=u, name=f"مريض اختبار {i}", blood_type=rnd.choice(["A+", "B+", "O+", "AB-"]))
                made += 1
            self.stdout.write(f"load-test patients created: {made}")
