"""Requests to the sign-up email helper (POST /api/auth/signup-email), kept
only to rate-limit it per email address and per client IP.

Neither the address nor the IP is stored: each key is a SHA-256 digest
(app/routers/signup_email.py). Rows older than a day are deleted on the next
request. Clients have no grants on the table (migration c4f8e2a6d1b3).
"""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, Text

from app.database import Base


class SignupEmailRequest(Base):
    __tablename__ = "signup_email_requests"
    __table_args__ = (
        Index("signup_email_requests_email_idx", "email_key", "created_at"),
        Index("signup_email_requests_ip_idx", "ip_key", "created_at"),
        Index("signup_email_requests_created_idx", "created_at"),
    )

    # BigInteger on Postgres; SQLite only autoincrements a plain INTEGER key.
    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    email_key = Column(Text, nullable=False)
    ip_key = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
