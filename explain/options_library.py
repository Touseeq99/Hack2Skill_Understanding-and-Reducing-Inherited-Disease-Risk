"""Neutral, equally weighted reproductive-options library (PDF section 5, requirement 2).

Rules enforced by tests:
- every option has the same structure and comparable length (no option is made to look better),
- every description ends with the same non-directive sentence,
- no ranking, recommendation or success-rate claim appears in the text,
- 'detailed' options are released by tier: for T2/T3 cases they unlock after counselling has happened.

DRAFT - requires clinical sign-off and cultural review by a licensed genetic counsellor.
"""

from typing import Any, Dict, List

CLOSING = {
    "en": "Some couples choose this; others choose differently. The decision is yours.",
    "ar": "يختار بعض الأزواج هذا الخيار ويختار غيرهم خياراً آخر. القرار يعود لكما.",
}

# detail_level: "general" options are always visible; "detailed" ones are released after counselling for T2/T3.
OPTIONS: List[Dict[str, Any]] = [
    {"id": "no_change", "detail_level": "general", "icon": "🌿",
     "title": {"en": "Continue with your current plans", "ar": "المضي في خططكما الحالية"},
     "body": {"en": "Plan a pregnancy naturally while knowing the chance in each pregnancy, with regular antenatal care.",
              "ar": "التخطيط لحمل طبيعي مع معرفة الاحتمال في كل حمل، ومتابعة منتظمة أثناء الحمل."}},
    {"id": "partner_testing", "detail_level": "general", "icon": "🧬",
     "title": {"en": "Further testing for you or your partner", "ar": "فحوصات إضافية لكِ أو للشريك"},
     "body": {"en": "Confirm a result or test more genes, so the picture for your couple is as clear as it can be.",
              "ar": "تأكيد نتيجة أو فحص جينات إضافية ليصبح تصوركما المشترك أوضح ما يمكن."}},
    {"id": "family_testing", "detail_level": "general", "icon": "👪",
     "title": {"en": "Testing for relatives", "ar": "الفحص للأقارب"},
     "body": {"en": "Relatives may also carry the same change; they can choose to be tested privately and in their own time.",
              "ar": "قد يحمل الأقارب التغير نفسه، ويمكنهم اختيار الفحص بخصوصية وفي الوقت الذي يناسبهم."}},
    {"id": "prenatal", "detail_level": "detailed", "icon": "🩺",
     "title": {"en": "Testing during pregnancy", "ar": "الفحص أثناء الحمل"},
     "body": {"en": "A test in early or mid pregnancy (such as CVS or amniocentesis) can show whether the baby inherited the condition.",
              "ar": "فحص في بداية الحمل أو منتصفه (مثل خزعة المشيمة أو السائل الأمنيوسي) يبيّن إن كان الجنين قد ورث الحالة."}},
    {"id": "pgt_m", "detail_level": "detailed", "icon": "🔬",
     "title": {"en": "IVF with embryo testing (PGT-M)", "ar": "أطفال الأنابيب مع فحص الأجنة (PGT-M)"},
     "body": {"en": "Embryos made through IVF are tested for the condition before one is transferred to the womb.",
              "ar": "تُفحص الأجنة الناتجة عن أطفال الأنابيب بحثاً عن الحالة قبل نقل أحدها إلى الرحم."}},
    {"id": "donor", "detail_level": "detailed", "icon": "🤲",
     "title": {"en": "Donor eggs or sperm", "ar": "التبرع بالبويضات أو الحيوانات المنوية"},
     "body": {"en": "Using donated eggs or sperm from a donor who does not carry the same change, where permitted and available.",
              "ar": "استخدام بويضات أو حيوانات منوية من متبرع لا يحمل التغير نفسه، حيثما يكون ذلك مسموحاً ومتاحاً."}},
    {"id": "adoption", "detail_level": "detailed", "icon": "🏡",
     "title": {"en": "Adoption or family sponsorship (kafala)", "ar": "التبني أو الكفالة الأسرية"},
     "body": {"en": "Building a family by caring for a child through the sponsorship routes available in the UAE.",
              "ar": "تكوين أسرة برعاية طفل عبر مسارات الكفالة المتاحة في دولة الإمارات."}},
]


def options_for(language: str, tier: str, case_state: str) -> List[Dict[str, Any]]:
    """Return the options with a `locked` flag. Detailed options for T2/T3 unlock after counselling."""
    lang = language if language in ("en", "ar") else "en"
    counselled = case_state in ("attended", "closed")
    gate = tier in ("T2", "T3") and not counselled
    out = []
    for o in OPTIONS:
        locked = gate and o["detail_level"] == "detailed"
        out.append({
            "id": o["id"],
            "icon": o["icon"],
            "title": o["title"][lang],
            "body": None if locked else f"{o['body'][lang]} {CLOSING[lang]}",
            "locked": locked,
            "locked_reason": (
                "Details are shared with you during your counselling session, so they can be explained properly."
                if lang == "en" else
                "تُشرح تفاصيل هذا الخيار خلال جلسة الاستشارة ليكون الشرح وافياً."
            ) if locked else None,
        })
    return out
