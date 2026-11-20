"""Safety resources and counsellor-hours logic (PDF section 4: out-of-hours T3 shows crisis contacts at once).

CONTACT DETAILS MUST BE VERIFIED by the clinical partner before any real use (flagged in the payload).
UAE has no daylight saving, so a fixed UTC+4 offset is used (no tzdata dependency).
"""

import datetime
from typing import Any, Dict, Optional

UAE_TZ = datetime.timezone(datetime.timedelta(hours=4))
COUNSELLOR_HOURS = (8, 17)      # 08:00-17:00 local
WORKING_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday-Friday

SAFETY_RESOURCES: Dict[str, Any] = {
    "verify_before_use": True,
    "emergency": [
        {"name_en": "Police / emergency", "name_ar": "الشرطة / الطوارئ", "number": "999"},
        {"name_en": "Ambulance", "name_ar": "الإسعاف", "number": "998"},
    ],
    "support": [
        {"name_en": "National mental-health support line (800 HOPE)", "name_ar": "الخط الوطني للدعم النفسي (800 أمل)", "number": "800-4673"},
    ],
    "message_en": "You are not alone. If you are in immediate danger or thinking of harming yourself, call 999 or 998 now. A genetic counsellor will also contact you.",
    "message_ar": "لستِ وحدكِ. إذا كنتِ في خطر مباشر أو تفكرين بإيذاء نفسك فاتصلي بـ 999 أو 998 الآن. وسيتواصل معكِ مرشد وراثي أيضاً.",
}


def is_out_of_hours(now: Optional[datetime.datetime] = None) -> bool:
    local = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(UAE_TZ)
    return local.weekday() not in WORKING_WEEKDAYS or not (COUNSELLOR_HOURS[0] <= local.hour < COUNSELLOR_HOURS[1])


def next_counsellor_window(now: Optional[datetime.datetime] = None) -> str:
    """ISO time of the next opening of counsellor hours (UAE local)."""
    local = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(UAE_TZ)
    cand = local.replace(hour=COUNSELLOR_HOURS[0], minute=0, second=0, microsecond=0)
    if cand <= local:
        cand += datetime.timedelta(days=1)
    while cand.weekday() not in WORKING_WEEKDAYS:
        cand += datetime.timedelta(days=1)
    return cand.isoformat()
