"""Clinician-approved template catalog in English and Arabic.
Supports 'standard' and 'simple' reading levels.
Marked: 'DRAFT - requires clinical sign-off'.
"""

from typing import Dict, Any

CLINICAL_SIGNOFF_TAG = "DRAFT - requires clinical sign-off"

TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    "SCREEN_NEGATIVE": {
        "en": {
            "standard": (
                "Your screening panel did not find any pathogenic carrier changes for the conditions tested. "
                "This significantly lowers your chance of having a child with these specific conditions, but it does not remove all risk. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "Your test came back clear for the conditions checked. "
                "This means your chance of passing on these conditions is much lower. "
                "However, no test can check for everything. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "لم يُظهر فحصك الجيني أي تغيرات مسببة للأمراض في الحالات الوراثية التي شملها الفحص. "
                "هذه النتيجة تقلل بشكل كبير من احتمالية انتقال هذه الحالات للأبناء، ولكنها لا تلغي الخطر تماماً لوجود احتمالية متبقية عامة. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "نتيجتك مطمئنة وسليمة بالنسبة للأمراض التي تم فحصها. "
                "هذا يعني أن فرصة إنجاب طفل مصاب بهذه الأمراض منخفضة جداً، مع بقاء نسبة عامة بسيطة. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "CARRIER_AR_SUMMARY": {
        "en": {
            "standard": (
                "You carry one changed copy of the {gene} gene, associated with {condition_name}. "
                "Carriers are typically healthy and do not experience symptoms. "
                "Carrier status is only clinically significant for future pregnancies if your partner carries a change in the exact same gene. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "You carry one working copy and one changed copy of the {gene} gene for {condition_name}. "
                "You are healthy. Being a carrier only matters if your partner also carries the same gene. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "أنت تحمل نسخة متغيرة واحدة من جين {gene}، المرتبط بـ {condition_name}. "
                "حاملو الجين يتمتعون عادةً بصحة ممتازة ولا تظهر عليهم أي أعراض. "
                "صفة الحامل تكون مهمة فقط في التخطيط للإنجاب إذا كان شريك الحياة حاملاً لنفس الجين تماماً. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "أنت حامل لنسخة متغيرة في جين {gene} المرتبط بـ {condition_name}. "
                "صحتك طبيعية تماماً. هذا الأمر يهم فقط عند الزواج إذا كان الطرف الآخر حاملاً لنفس الجين. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "COUPLE_SAME_GENE_NUMBERS": {
        "en": {
            "standard": (
                "Both you and your partner carry a changed copy of the {gene} gene for {condition_name}. "
                "In each pregnancy, there is a 1 in 4 chance of having an affected child, "
                "a 1 in 2 chance of having a healthy carrier child, and a 1 in 4 chance of having a child who is neither affected nor a carrier. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "You both carry a change in the {gene} gene for {condition_name}. "
                "In every pregnancy: 1 in 4 chance the child has the condition, "
                "1 in 2 chance the child is a healthy carrier like you, and 1 in 4 chance the child does not carry the change. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "كلاكما يحمل تغيراً في جين {gene} المرتبط بـ {condition_name}. "
                "في كل حمل مستقل، تكون الاحتمالات كالتالي: احتمال 1 من 4 أن يولد طفل مصاب بالحالة، "
                "واحتمال 1 من 2 أن يكون الطفل حاملاً سليماً للصفة مثلكما، واحتمال 1 من 4 أن يكون سليماً تماماً وغير حامل للصفة. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "أنتما الاثنان تحملان تغيراً في جين {gene} الخاص بـ {condition_name}. "
                "في كل حمل: هناك احتمال 1 من 4 أن يولد طفل مصاب، و1 من 2 أن يكون طفلاً حاملاً بصحة جيدة، و1 من 4 أن يكون سليماً تماماً. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "COUPLE_NO_SHARED_GENE": {
        "en": {
            "standard": (
                "No shared genetic carrier changes were identified between you and your partner among the conditions screened. "
                "Your chance of having a child affected by these conditions is at standard baseline population levels. "
                "Residual risk remains present as with all screening tests. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "Good news: You and your partner do not share any carrier changes on this test. "
                "Your risk for these conditions is very low, though general population chances always remain. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "لم يتم العثور على أي تغيرات جينية مشتركة بينكما في قائمة الحالات الوراثية المفحوصة. "
                "احتمالية إنجاب طفل مصاب بهذه الحالات تقع ضمن المعدل العام المنخفض في المجتمع. "
                "تبقى هناك نسبة احتمالية متبقية عامة كما في جميع الفحوصات الطبية. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "خبر مطمئن: لا يوجد جين مشترك بينكما في الأمراض التي فُحصت. "
                "الفرصة منخفضة جداً للإصابة بهذه الأمراض، مع بقاء النسبة العامة الطبيعية لأي حمل. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "UNCERTAINTY_VUS": {
        "en": {
            "standard": (
                "A Variant of Uncertain Significance (VUS) was detected in the {gene} gene. "
                "Current clinical scientific knowledge does not yet confirm whether this variation causes health effects or is a harmless natural variation. "
                "It is not treated as a positive carrier result, and no numeric probability can be calculated. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "We found a genetic change of unknown meaning in {gene}. "
                "Science does not yet know if it causes any problem or is just normal variation. "
                "We do not treat it as a carrier result, and cannot give a percentage. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "تم رصد تغير جيني غير محدد الأهمية السريرية (VUS) في جين {gene}. "
                "المعلومات الطبية الحالية حول العالم لا تؤكد بعد ما إذا كان هذا التغير غير ضار أم له تأثير صحي. "
                "لذلك لا يُعامل كنتيجة حامل مؤكدة، ولا يمكن حساب نسبة رقمية محددة. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "تم العثور على تغير جيني في {gene} لم يحدد العلم معناه بعد. "
                "لا نعتبر هذا التغير مرضاً وراثياً مؤكداً، ولا يمكن إعطاء نسبة رقمية له. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "XLINKED_FEMALE_CARRIER": {
        "en": {
            "standard": (
                "You carry an X-linked variant in {gene}, associated with {condition_name}. "
                "In each pregnancy: each son has a 1 in 2 chance of being affected; each daughter has a 1 in 2 chance of being a carrier. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "You carry an X-linked change in {gene} for {condition_name}. "
                "Each boy has a 1 in 2 chance of having the condition; each girl has a 1 in 2 chance of being a carrier. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "تحملين تغيراً جينياً مرتبطاً بالصبغي X في جين {gene} الخاص بـ {condition_name}. "
                "في كل حمل: لكل جنين ذكر احتمال 1 من 2 أن يكون مصاباً؛ ولكل جنين أنثى احتمال 1 من 2 أن تكون حاملة للصفة. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "أنتِ حاملة لتغير على الصبغي X في جين {gene}. "
                "كل مولود ذكر لديه احتمال 1 من 2 للإصابة، وكل مولودة أنثى لديها احتمال 1 من 2 أن تكون حاملة مثلك. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "POSSIBLE_AFFECTED": {
        "en": {
            "standard": (
                "Two pathogenic changes were found in the {gene} gene ({condition_name}). "
                "This is not a typical carrier screening result and requires direct clinical and specialist evaluation. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "Two genetic changes were found in {gene} for {condition_name}. "
                "This is not a carrier result. A doctor or genetic specialist needs to review this with you directly. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "تم العثور على تغيرين جينيين مسببين للمرض في جين {gene} المرتبط بـ {condition_name}. "
                "هذه ليست مجرد نتيجة حامل للجين، وتتطلب مراجعة سريرية متخصصة ومباشرة مع طبيب الوراثة. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "وُجد تغيران في جين {gene}. هذه النتيجة تستدعي مراجعة مباشرة مع استشاري الوراثة لمعرفة تفاصيلها. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },

    "DIRECTIVE_QUESTION_HANDOFF": {
        "en": {
            "standard": (
                "We understand you may wonder whether to proceed with marriage or what choices are best. "
                "As an educational platform, we never advise on personal relationship or marriage decisions. "
                "Some couples choose to proceed with pre-implantation testing (PGT-M), others choose prenatal testing, "
                "and others choose to proceed naturally. A licensed genetic counsellor is available to discuss your values and options confidentially. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "Decisions about marriage and children are completely personal to you and your partner. "
                "We never tell you what to do. Different families explore different choices, like PGT-M or natural pregnancy. "
                "We have connected you with a human genetic counsellor to talk through all choices together. "
                "This is a screening result, not a diagnosis. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
        "ar": {
            "standard": (
                "نتفهم تماماً تساؤلاتكما حول المضي قدماً في الزواج أو الخيارات الأنسب لمستقبلكما. "
                "كمنصة توعوية وطبية محايدة، نحن لا نقدم إطلاقاً أي نصيحة بالزواج أو عدمه، فالقرار يعود لكما بالكامل. "
                "بعض الأزواج يختارون فحص الأجنة الوراثي (PGT-M)، وآخرون يختارون الفحص أثناء الحمل، وآخرون يتابعون بصورة طبيعية. "
                "لقد تم حجز موعد مع مستشار وراثي متخصص لمناقشة كافة الخيارات بخصوصية تامة ودعم كامل. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
            "simple": (
                "قرارات الزواج والأسرة هي قرارات شخصية خاصة بكما تماماً، ونحن لا ننصح أبداً بما يجب فعله. "
                "هناك خيارات طبية متعددة ومتاحة يختار منها كل زوجين ما يناسبهما. "
                "يمكنكما التحدث مع مستشار وراثي لمساعدتكما في فهم كافة الخيارات المتاحة بكل راحة واطمئنان. "
                "هذا فحص استكشافي وليس تشخيصاً طبياً. "
                f"[{CLINICAL_SIGNOFF_TAG}]"
            ),
        },
    },
}

# Template metadata mapping with version and approved_by fields
TEMPLATE_METADATA: Dict[str, Dict[str, Any]] = {
    key: {
        "id": key,
        "version": "v1",
        "approved_by": CLINICAL_SIGNOFF_TAG,
        "languages": ["en", "ar"],
        "reading_levels": ["standard", "simple"],
    }
    for key in TEMPLATES.keys()
}


def get_template_entry(key: str, language: str = "ar", reading_level: str = "standard") -> Dict[str, Any]:
    """Retrieve template text alongside version and approved_by metadata."""
    if key not in TEMPLATES:
        raise KeyError(f"Template key '{key}' not found.")
    meta = TEMPLATE_METADATA[key]
    lang_dict = TEMPLATES[key].get(language, TEMPLATES[key]["en"])
    text = lang_dict.get(reading_level, lang_dict["standard"])
    return {
        "id": key,
        "language": language,
        "reading_level": reading_level,
        "body": text,
        "version": meta["version"],
        "approved_by": meta["approved_by"],
    }
