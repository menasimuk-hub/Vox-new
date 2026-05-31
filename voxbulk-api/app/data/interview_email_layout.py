"""Interview email layout — delegates to shared brand wrapper."""

from __future__ import annotations

from app.data.brand_email_layout import cta_button, wrap_brand_email

wrap_interview_email = wrap_brand_email

__all__ = ["wrap_interview_email", "cta_button"]
