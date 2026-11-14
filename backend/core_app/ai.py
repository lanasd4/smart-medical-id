"""Health guide (triage) and clinical assistant: Ollama with a rule-based fallback."""
import json
import logging
import re
import time

from django.conf import settings
from django.utils import timezone

from .models import (
    SPECIALTIES, SPECIALTY_CODES, Allergy, Condition, Medication, Observation, Procedure,
)
from .ollama_client import chat_generic

log = logging.getLogger(__name__)
SPECIALTY_LABELS = dict(SPECIALTIES)
MAX_QUESTIONS = 4
DISCLAIMER = "هذه إرشادات أولية ولا تغني عن الفحص الطبي. في الحالات الطارئة اتصل بالإسعاف فوراً."

# ---------------------------------------------------------------------------
# Patient record snapshot (compact, for prompts and the doctor summary)
# ---------------------------------------------------------------------------

def _age(dob):
    if not dob:
        return None
    today = timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def record_snapshot(patient):
    conditions = [
        {"name": c.display_name, "chronic": c.is_chronic, "status": c.status or ""}
        for c in Condition.objects.filter(patient=patient).select_related("code")[:50]
    ]
    meds = [
        {"name": m.local_name or (m.code.name if m.code_id else ""), "dose": m.dose or "", "status": m.status or ""}
        for m in Medication.objects.filter(patient=patient).select_related("code")[:50]
    ]
    allergies = [
        {"substance": a.substance, "reaction": a.reaction or "", "severity": a.severity or ""}
        for a in Allergy.objects.filter(patient=patient)[:50]
    ]
    surgeries = [
        {"name": p.name, "date": p.performed_on.isoformat() if p.performed_on else ""}
        for p in Procedure.objects.filter(patient=patient)[:30]
    ]
    vitals = [
        {"name": o.code.name if o.code_id else "", "value": o.value, "unit": o.unit or "",
         "at": o.observed_at.date().isoformat() if o.observed_at else ""}
        for o in Observation.objects.filter(patient=patient).select_related("code").order_by("-observed_at")[:15]
    ]
    return {
        "age": _age(patient.date_of_birth),
        "gender": patient.gender or "",
        "blood_type": patient.blood_type or "",
        "height_cm": float(patient.height_cm) if patient.height_cm else None,
        "weight_kg": float(patient.weight_kg) if patient.weight_kg else None,
        "conditions": conditions,
        "medications": meds,
        "allergies": allergies,
        "surgeries": surgeries,
        "recent_observations": vitals,
    }

# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

RULES = [
    # (specialty, keywords, possible conditions, recommended tests)
    ("CARDIOLOGY", ["ألم صدر", "ألم في الصدر", "وجع صدر", "خفقان", "دقات القلب", "ضغط الدم", "ضغط مرتفع",
                    "chest pain", "palpitation", "hypertension"],
     ["ذبحة صدرية", "اضطراب نظم القلب", "ارتفاع ضغط الدم"],
     ["تخطيط قلب كهربائي ECG", "إنزيمات القلب (Troponin)", "شحوم الدم", "إيكو قلب"]),
    ("PULMONOLOGY", ["سعال", "سعلة", "كحة", "ضيق تنفس", "ضيق نفس", "صفير", "ربو", "بلغم",
                     "cough", "shortness of breath", "wheez", "asthma"],
     ["التهاب قصبات", "ربو", "التهاب رئة"],
     ["صورة صدر شعاعية", "تعداد دم كامل CBC", "اختبار وظائف الرئة", "إشباع الأكسجين"]),
    ("GASTRO", ["ألم بطن", "ألم في البطن", "وجع بطن", "مغص", "إسهال", "اسهال", "إمساك", "امساك", "غثيان",
                "إقياء", "استفراغ", "حرقة معدة", "حموضة", "انتفاخ", "abdominal", "diarrhea", "nausea", "vomit"],
     ["التهاب معدة", "القولون العصبي", "ارتجاع مريئي", "التهاب أمعاء"],
     ["تعداد دم كامل CBC", "وظائف الكبد", "تحليل براز", "إيكو بطن"]),
    ("NEUROLOGY", ["صداع", "شقيقة", "دوخة", "دوار", "تنميل", "خدر", "رجفة", "اختلاج", "نوبة", "ضعف في الطرف",
                   "headache", "migraine", "dizz", "numb", "seizure"],
     ["صداع توتري", "شقيقة", "اعتلال أعصاب محيطية"],
     ["فحص عصبي سريري", "فيتامين B12", "سكر الدم", "طبقي محوري للرأس عند الحاجة"]),
    ("DERMATOLOGY", ["حكة", "طفح", "حب شباب", "بقع", "جلد", "أكزيما", "اكزيما", "تساقط شعر", "rash", "itch", "acne", "eczema"],
     ["التهاب جلد تحسسي", "أكزيما", "عدوى فطرية"],
     ["فحص جلدي سريري", "اختبار تحسس", "مسحة فطرية عند الحاجة"]),
    ("ENT", ["أذن", "اذن", "حلق", "بلعوم", "لوزات", "لوز", "انسداد أنف", "جيوب", "رعاف", "طنين",
             "ear", "throat", "sinus", "tonsil"],
     ["التهاب لوزات", "التهاب جيوب", "التهاب أذن وسطى"],
     ["فحص أذن وأنف وحنجرة", "مسحة حلق", "تعداد دم كامل CBC"]),
    ("OPHTHALMOLOGY", ["عين", "عيون", "رؤية", "نظر", "زغللة", "احمرار العين", "eye", "vision", "blurred"],
     ["التهاب ملتحمة", "خطأ انكساري", "جفاف عين"],
     ["فحص قاع العين", "قياس حدة البصر", "قياس ضغط العين"]),
    ("UROLOGY", ["حرقة بول", "حرقة بالبول", "ألم عند التبول", "تبول متكرر", "دم في البول", "بروستات",
                 "urine", "urinary", "prostate"],
     ["التهاب مجاري بولية", "حصيات بولية", "تضخم بروستات"],
     ["تحليل بول كامل", "زرع بول", "إيكو جهاز بولي"]),
    ("NEPHROLOGY", ["كلية", "كلى", "قصور كلوي", "تورم القدمين", "kidney", "renal"],
     ["قصور كلوي", "التهاب كلية"],
     ["وظائف الكلية (كرياتينين، يوريا)", "تحليل بول كامل", "الشوارد"]),
    ("ORTHOPEDICS", ["ركبة", "ظهر", "ألم الظهر", "رقبة", "كتف", "كسر", "التواء", "عظم", "مفصل",
                     "back pain", "knee", "fracture", "sprain", "shoulder"],
     ["إجهاد عضلي", "انزلاق غضروفي", "التهاب مفصل"],
     ["صورة شعاعية للمنطقة", "رنين مغناطيسي عند الحاجة", "فيتامين D"]),
    ("RHEUMATOLOGY", ["تيبس صباحي", "روماتيزم", "آلام مفاصل متعددة", "تورم المفاصل", "نقرس", "lupus", "gout"],
     ["التهاب مفاصل رثياني", "نقرس", "ذئبة"],
     ["عامل رثياني RF", "Anti-CCP", "سرعة تثفل ESR", "CRP", "حمض البول"]),
    ("ENDOCRINOLOGY", ["سكري", "سكر", "عطش", "كثرة التبول", "غدة", "درق", "نقص وزن", "زيادة وزن",
                       "diabetes", "thyroid", "thirst"],
     ["داء السكري", "قصور أو فرط نشاط الدرق"],
     ["سكر صائم", "خضاب سكري HbA1c", "هرمونات الدرق TSH/T4"]),
    ("OBGYN", ["حمل", "حامل", "دورة", "الدورة الشهرية", "طمث", "نزف مهبلي", "إفرازات", "pregnan", "period", "menstrua"],
     ["اضطراب دورة", "التهاب حوض", "متابعة حمل"],
     ["اختبار حمل", "إيكو حوض", "هرمونات أنثوية"]),
    ("PSYCHIATRY", ["قلق", "اكتئاب", "توتر", "أرق", "نوبات هلع", "حزن", "anxiety", "depress", "insomnia", "panic"],
     ["اضطراب قلق", "اكتئاب", "أرق"],
     ["تقييم نفسي", "هرمونات الدرق لاستبعاد سبب عضوي"]),
    ("DENTISTRY", ["سن", "أسنان", "ضرس", "لثة", "tooth", "teeth", "gum"],
     ["تسوس", "التهاب لثة", "خراج سني"],
     ["فحص سني", "صورة بانورامية"]),
]

RED_FLAGS = [
    ("ألم صدر", "ألم في الصدر"), ("ضيق تنفس شديد",), ("فقدان وعي", "إغماء", "غياب عن الوعي"),
    ("نزيف شديد", "نزف شديد"), ("شلل", "ضعف مفاجئ", "صعوبة كلام", "ارتخاء الوجه"),
    ("أفكار انتحارية", "انتحار"), ("قيء دموي", "براز أسود"), ("حرارة فوق 40",),
]

RULE_QUESTIONS = [
    {"question": "منذ متى بدأت هذه الأعراض؟",
     "options": ["أقل من 24 ساعة", "من 1 إلى 3 أيام", "حوالي أسبوع", "أكثر من أسبوعين"]},
    {"question": "كيف تقيّم شدة الأعراض؟",
     "options": ["خفيفة", "متوسطة", "شديدة", "لا تُحتمل"]},
    {"question": "هل ترافقها حرارة أو أعراض أخرى؟ (اكتب ما تلاحظه أو اختر)",
     "options": ["لا يوجد", "حرارة", "تعب عام", "فقدان شهية"]},
]


def _norm(text):
    text = (text or "").lower()
    return re.sub("[إأآا]", "ا", text).replace("ة", "ه").replace("ى", "ي")


def _contains(text, words):
    t = _norm(text)
    return any(_norm(w) in t for w in words)


def rules_result(user_texts, snapshot):
    text = " \n".join(user_texts)
    scores = []
    for spec, words, conds, tests in RULES:
        hits = sum(1 for w in words if _norm(w) in _norm(text))
        if hits:
            scores.append((hits, spec, conds, tests))
    scores.sort(key=lambda x: -x[0])

    age = snapshot.get("age")
    if scores:
        _, specialty, conditions, tests = scores[0]
    else:
        specialty, conditions, tests = "INTERNAL", ["يحتاج تقييماً سريرياً عاماً"], ["تعداد دم كامل CBC", "سكر الدم", "وظائف كلية وكبد"]
    if age is not None and age < 14 and specialty not in ("DENTISTRY", "OPHTHALMOLOGY", "ENT"):
        specialty = "PEDIATRICS"

    red = [group[0] for group in RED_FLAGS if _contains(text, group)]
    severe = _contains(text, ["لا تحتمل", "شديده", "شديدة"])
    if red:
        urgency = "er"
    elif severe or _contains(text, ["اقل من 24 ساعه"]) and _contains(text, ["حراره"]):
        urgency = "urgent"
    elif _contains(text, ["اكثر من اسبوعين"]):
        urgency = "routine"
    else:
        urgency = "soon"

    chronic = [c["name"] for c in snapshot.get("conditions", []) if c.get("chronic") or (c.get("status") or "").lower() == "active"]
    if any(_contains(c, ["سكري", "diabetes"]) for c in chronic) and "خضاب سكري HbA1c" not in tests:
        tests = tests + ["خضاب سكري HbA1c"]

    advice = {
        "er": "توجّه إلى أقرب قسم إسعاف فوراً أو اتصل بالإسعاف، ولا تنتظر موعداً.",
        "urgent": "يُفضّل مراجعة الطبيب خلال 24 ساعة.",
        "soon": "احجز موعداً خلال الأيام القليلة القادمة، وراقب تطور الأعراض.",
        "routine": "يمكنك حجز موعد عادي، مع الاهتمام بالراحة والسوائل.",
    }[urgency]
    if urgency == "er":
        specialty = "EMERGENCY"
    return _finalize({
        "specialty": specialty,
        "urgency": urgency,
        "possible_conditions": conditions[:4],
        "recommended_tests": tests[:6],
        "red_flags": red,
        "advice": advice,
        "summary": text[:400],
    }, snapshot, user_texts, engine="rules")


def _finalize(result, snapshot, user_texts, engine):
    spec = result.get("specialty") if result.get("specialty") in SPECIALTY_CODES else "INTERNAL"
    result["specialty"] = spec
    result["specialty_label"] = SPECIALTY_LABELS.get(spec, spec)
    if result.get("urgency") not in ("routine", "soon", "urgent", "er"):
        result["urgency"] = "soon"
    for key in ("possible_conditions", "recommended_tests", "red_flags"):
        val = result.get(key) or []
        result[key] = [str(v) for v in val][:8] if isinstance(val, list) else [str(val)]
    result["advice"] = str(result.get("advice") or "")
    result["disclaimer"] = DISCLAIMER
    result["engine"] = engine
    # Structured note for the doctor (attached to the appointment if the patient books)
    result["doctor_summary"] = {
        "chief_complaint": user_texts[0][:300] if user_texts else "",
        "answers": user_texts[1:],
        "suspected": result["possible_conditions"],
        "suggested_tests": result["recommended_tests"],
        "urgency": result["urgency"],
        "relevant_history": {
            "conditions": [c["name"] for c in snapshot.get("conditions", [])][:10],
            "medications": [m["name"] for m in snapshot.get("medications", []) if m["name"]][:10],
            "allergies": [a["substance"] for a in snapshot.get("allergies", [])][:10],
            "surgeries": [s["name"] for s in snapshot.get("surgeries", [])][:10],
            "blood_type": snapshot.get("blood_type"),
            "age": snapshot.get("age"),
        },
    }
    return result

# ---------------------------------------------------------------------------
# LLM engine
# ---------------------------------------------------------------------------

def _llm_system_prompt(snapshot):
    specs = ", ".join(f"{c} ({l})" for c, l in SPECIALTIES)
    return (
        "أنت \"الدليل الصحي\" في تطبيق الهوية الطبية الذكية. مهمتك فرز أولي وليس تشخيصاً نهائياً.\n"
        "اقرأ شكوى المريض وسجله الطبي، ثم اطرح سؤالاً تشخيصياً واحداً في كل مرة (بحد أقصى "
        f"{MAX_QUESTIONS} أسئلة) لتحديد الاختصاص المناسب. عندما تكتمل المعلومات أعطِ النتيجة النهائية.\n"
        "أجب دائماً بـ JSON فقط وبالعربية، بأحد الشكلين:\n"
        '{"type":"question","question":"...","options":["...","..."]}\n'
        '{"type":"result","specialty":"CODE","urgency":"routine|soon|urgent|er","possible_conditions":["..."],'
        '"recommended_tests":["..."],"red_flags":["..."],"advice":"...","summary":"..."}\n'
        f"رموز الاختصاصات المسموحة فقط: {specs}\n"
        "لا تذكر جرعات أدوية. إذا وُجدت علامات خطر (ألم صدر شديد، ضيق تنفس شديد، فقدان وعي، نزيف، علامات جلطة) "
        "أعطِ النتيجة فوراً مع urgency=er و specialty=EMERGENCY.\n"
        "السجل الطبي للمريض:\n" + json.dumps(snapshot, ensure_ascii=False, default=str)
    )


def _llm_turn(session, snapshot, force_result=False):
    msgs = [{"role": "system", "content": _llm_system_prompt(snapshot)}]
    for m in session.messages:
        if m["role"] == "user":
            msgs.append({"role": "user", "content": m["content"]})
        else:
            msgs.append({"role": "assistant", "content": json.dumps(m.get("data") or {"type": "question", "question": m["content"]}, ensure_ascii=False)})
    if force_result:
        msgs.append({"role": "user", "content": "اكتفِ بالأسئلة. أعطِ النتيجة النهائية الآن بصيغة JSON من النوع result."})
    resp = chat_generic({
        "messages": msgs, "format": "json", "temperature": 0.2, "num_ctx": 8192, "num_predict": 700,
    }, timeout=getattr(settings, "AI_TIMEOUT", 90))
    content = (resp.get("message") or {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    data = json.loads(content)
    if not isinstance(data, dict) or data.get("type") not in ("question", "result"):
        raise ValueError("bad llm payload")
    if data["type"] == "question" and not str(data.get("question", "")).strip():
        raise ValueError("empty question")
    return data


def ai_available():
    if not getattr(settings, "AI_ENABLED", True):
        return False
    import requests
    try:
        requests.get(f"{settings.OLLAMA_URL}/api/tags", timeout=1.5).raise_for_status()
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def triage_step(session, patient, user_message):
    """Append the user's message and produce the next assistant turn (question or result)."""
    snapshot = record_snapshot(patient)
    session.messages = list(session.messages) + [{"role": "user", "content": user_message.strip()[:2000],
                                                   "at": timezone.now().isoformat()}]
    user_texts = [m["content"] for m in session.messages if m["role"] == "user"]
    asked = sum(1 for m in session.messages if m["role"] == "assistant" and (m.get("data") or {}).get("type") == "question")

    # Red flags short-circuit straight to an emergency result, whatever the engine
    if any(_contains(" ".join(user_texts), g) for g in RED_FLAGS):
        result = rules_result(user_texts, snapshot)
        return _complete(session, result)

    data = None
    if session.engine != "rules" and ai_available():
        try:
            started = time.monotonic()
            data = _llm_turn(session, snapshot, force_result=asked >= MAX_QUESTIONS)
            if data["type"] == "question" and asked >= MAX_QUESTIONS:
                data = _llm_turn(session, snapshot, force_result=True)
            session.engine = "ollama"
            log.info("triage llm turn %.1fs", time.monotonic() - started)
        except Exception as exc:
            log.warning("LLM triage failed, falling back to rules: %s", exc)
            session.engine = "rules"
            data = None
    else:
        session.engine = "rules"

    if data is None:  # rule engine: fixed diagnostic questions then result
        if asked < len(RULE_QUESTIONS):
            q = RULE_QUESTIONS[asked]
            data = {"type": "question", "question": q["question"], "options": q["options"]}
        else:
            return _complete(session, rules_result(user_texts, snapshot))

    if data["type"] == "result":
        return _complete(session, _finalize(data, snapshot, user_texts, engine="ollama"))

    session.messages = session.messages + [{
        "role": "assistant", "content": str(data.get("question")),
        "data": {"type": "question", "question": str(data.get("question")),
                 "options": [str(o) for o in (data.get("options") or [])][:6]},
        "at": timezone.now().isoformat(),
    }]
    session.save()
    return session


def _complete(session, result):
    session.result = result
    session.status = session.COMPLETED
    session.messages = list(session.messages) + [{
        "role": "assistant", "content": result.get("advice", ""), "data": {"type": "result"},
        "at": timezone.now().isoformat(),
    }]
    session.save()
    return session


def doctor_assist(patient, question, latest_triage=None):
    """Answer a clinician's question about a patient using the full record."""
    snapshot = record_snapshot(patient)
    if latest_triage:
        snapshot["latest_triage"] = latest_triage
    if ai_available():
        try:
            resp = chat_generic({
                "messages": [
                    {"role": "system", "content": (
                        "أنت مساعد سريري لطبيب. أجب بالعربية بإيجاز وبنقاط، معتمداً فقط على السجل المرفق. "
                        "اقترح تشخيصات تفريقية وتحاليل مناسبة ونبّه إلى التداخلات الدوائية والتحسسات. "
                        "القرار النهائي للطبيب.\nالسجل:\n" + json.dumps(snapshot, ensure_ascii=False, default=str))},
                    {"role": "user", "content": question[:2000]},
                ],
                "temperature": 0.2, "num_predict": 700,
            }, timeout=getattr(settings, "AI_TIMEOUT", 90))
            text = re.sub(r"<think>.*?</think>", "", (resp.get("message") or {}).get("content", ""), flags=re.S).strip()
            text = re.sub(r"\*\*|__|^#{1,6}\s*", "", text, flags=re.M)  # plain text for the UI
            if text:
                return {"answer": text, "engine": "ollama"}
        except Exception as exc:
            log.warning("doctor assist LLM failed: %s", exc)

    # Fallback: structured clinical summary
    lines = ["ملخص سريري للمريض (المساعد الذكي غير متاح حالياً، هذا ملخص آلي):"]
    if snapshot["age"] is not None:
        lines.append(f"• العمر: {snapshot['age']} سنة — الجنس: {snapshot['gender'] or 'غير محدد'} — زمرة الدم: {snapshot['blood_type'] or 'غير محددة'}")
    if snapshot["conditions"]:
        lines.append("• الأمراض: " + "، ".join(c["name"] + (" (مزمن)" if c["chronic"] else "") for c in snapshot["conditions"]))
    if snapshot["medications"]:
        lines.append("• الأدوية: " + "، ".join(f"{m['name']} {m['dose']}".strip() for m in snapshot["medications"] if m["name"]))
    if snapshot["allergies"]:
        lines.append("• ⚠️ التحسسات: " + "، ".join(a["substance"] for a in snapshot["allergies"]))
    if snapshot["surgeries"]:
        lines.append("• العمليات السابقة: " + "، ".join(s["name"] for s in snapshot["surgeries"]))
    if latest_triage:
        lines.append(f"• آخر فرز ذكي: {latest_triage.get('specialty_label', '')} — الشدة: {latest_triage.get('urgency', '')}")
        if latest_triage.get("recommended_tests"):
            lines.append("• تحاليل مقترحة: " + "، ".join(latest_triage["recommended_tests"]))
    return {"answer": "\n".join(lines), "engine": "rules"}
