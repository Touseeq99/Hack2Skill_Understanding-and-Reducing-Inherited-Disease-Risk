"""Anonymous family cascade notice service.

Preserves privacy:
- Warns sender that choice of relatives may allow relatives to infer who sent it.
- Sender's name, ID, and specific test result are NEVER included in notice or exposed.
- Sender ID is cryptographically hashed before storing in database.
"""

import hashlib
import uuid
from typing import Dict, Any, Optional
from fastapi import HTTPException
from backend.database import Database, db
from backend.audit_log import audit_logger

NOTICE_SENDER_WARNING = (
    "Privacy Notice: While this message is sent anonymously by the platform and contains no name or test results, "
    "relatives may deduce your identity based on who you choose to inform or recent family conversations. "
    "Your name and test result will NEVER be disclosed."
)


class FamilyNoticeService:
    """Manages anonymous family cascade notifications."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.audit = audit_logger

    def _hash_sender(self, sender_id: str) -> str:
        salted = f"salt_family_notice_{sender_id}"
        return hashlib.sha256(salted.encode("utf-8")).hexdigest()

    def send_notice(
        self,
        sender_id: str,
        channel: str,
        condition_name: str,
        recipient_contact: str,
    ) -> Dict[str, Any]:
        """Create and queue an anonymous family cascade notice."""
        token = f"tok_{uuid.uuid4().hex[:12]}"
        notice_id = f"notif_{uuid.uuid4().hex[:12]}"
        sender_hash = self._hash_sender(sender_id)

        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO family_notice (id, sender_id_hash, channel, token, condition_name, opened, booked)
            VALUES (?, ?, ?, ?, ?, 0, 0)
        """, (notice_id, sender_hash, channel, token, condition_name))
        conn.commit()
        conn.close()

        # The message content sent to recipient contains NO sender identity or result
        message_body_en = (
            f"A family relative suggests you consider pre-marital / preconception carrier screening for {condition_name}. "
            f"Free confidential booking and information are available: https://screen.ad/notice/{token}"
        )
        message_body_ar = (
            f"يقترح أحد أفراد العائلة إجراء فحص التوافق الجيني الاستكشافي لـ {condition_name}. "
            f"للحجز والاطلاع بسرية تامة ومجاناً: https://screen.ad/notice/{token}"
        )

        # Audit log creation with zero identifiable payload
        self.audit.record_event(
            actor="system:family_notice",
            action="anonymous_notice_sent",
            target=f"notice:{notice_id}",
        )

        return {
            "notice_id": notice_id,
            "token": token,
            "channel": channel,
            "condition_name": condition_name,
            "warning": NOTICE_SENDER_WARNING,
            "message_en": message_body_en,
            "message_ar": message_body_ar,
            "sender_identity_disclosed": False,
        }

    def open_notice(self, token: str) -> Dict[str, Any]:
        """Record recipient opening notice link and return educational overview."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, condition_name, opened, booked FROM family_notice WHERE token = ?", (token,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Notice token not found or expired.")

        cur.execute("UPDATE family_notice SET opened = 1 WHERE token = ?", (token,))
        conn.commit()
        conn.close()

        self.audit.record_event(
            actor="relative:anonymous",
            action="notice_opened",
            target=f"notice:{row['id']}",
        )

        return {
            "status": "valid",
            "condition_name": row["condition_name"],
            "booking_link": f"/app?referral=notice_{token}",
            "info": "You were invited by a family relative to consider carrier screening. No personal details of the sender are shared.",
        }

    def generate_shareable_card(self, condition_name: str, language: str = "ar") -> Dict[str, Any]:
        """Generate an educational shareable explainer card (Option 1)."""
        card_content_ar = {
            "title": f"معلومات توعوية حول التوافق الوراثي: {condition_name}",
            "headline": "الفحص الجيني الاستكشافي للأسرة والمقبلين على الزواج",
            "body": (
                f"تشارك عائلتنا هذه البطاقة التوعوية لتشجيع المقبلين على الزواج على إجراء فحص التوافق الوراثي الاستكشافي لـ {condition_name}. "
                "كونك حاملاً للصفة الوراثية لا يعني إصابتك بأي مرض، بل يساعدك في التخطيط الإنجابي السليم. "
                "الفحص متوفر بسرية تامة ومجاناً عبر المنظومة الصحية في أبوظبي."
            ),
            "cta": "احجز موعد استشارة جينية استكشافية",
            "privacy_notice": "هذه البطاقة عامة ولا تتضمن أي بيانات شخصية أو نتائج خاصة بأي فرد.",
            "disclaimer": "هذا فحص استكشافي وليس تشخيصاً طبياً. [DRAFT - requires clinical sign-off]",
        }
        card_content_en = {
            "title": f"Family Health Education: {condition_name} Carrier Screening",
            "headline": "Pre-marital and Preconception Genetic Compatibility",
            "body": (
                f"Our family is sharing this informational card to encourage relatives planning marriage or pregnancy to consider carrier screening for {condition_name}. "
                "Being a carrier means having one changed copy of a gene—carriers are healthy. "
                "Confidential screening and accredited genetic counselling are freely available in Abu Dhabi."
            ),
            "cta": "Book a Free Genetic Consultation",
            "privacy_notice": "This informational card contains no names, personal data, or individual test results.",
            "disclaimer": "This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]",
        }
        return {
            "option": "option_1_shareable_card",
            "condition_name": condition_name,
            "language": language,
            "card": card_content_ar if language == "ar" else card_content_en,
        }


family_notice_svc = FamilyNoticeService()
