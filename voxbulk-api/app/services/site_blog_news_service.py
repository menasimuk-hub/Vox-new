"""CRUD + seed for marketing-site blog / news items."""

from __future__ import annotations

import html
import re
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.site_blog_news_item import SiteBlogNewsItem

KIND_BLOG = "blog"
KIND_NEWS = "news"
KINDS = frozenset({KIND_BLOG, KIND_NEWS})
BODY_MODES = frozenset({"text", "html"})

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SCRIPT_RE = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style[^>]*>.*?</style>")
_EVENT_ATTR_RE = re.compile(r"""(?is)\s+on[a-z]+\s*=\s*(['"]).*?\1""")
_JS_HREF_RE = re.compile(r"""(?is)\s+(href|src)\s*=\s*(['"])\s*javascript:[^'"]*\2""")


def slugify(title: str) -> str:
    base = (title or "").strip().lower()
    base = _SLUG_RE.sub("-", base).strip("-")
    return (base or "item")[:160]


def sanitize_html(raw: str) -> str:
    text = raw or ""
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    text = _EVENT_ATTR_RE.sub("", text)
    text = _JS_HREF_RE.sub("", text)
    return text


def normalize_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in KINDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="kind must be blog or news")
    return k


def normalize_body_mode(mode: str | None) -> str:
    m = (mode or "text").strip().lower()
    if m not in BODY_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="body_mode must be text or html")
    return m


def item_to_dict(row: SiteBlogNewsItem, *, include_admin: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "kind": row.kind,
        "slug": row.slug,
        "title": row.title,
        "excerpt": row.excerpt or "",
        "category": row.category or "General",
        "author": row.author or "VoxBulk",
        "author_role": row.author_role or "",
        "image_url": row.image_url,
        "body_mode": row.body_mode,
        "body": row.body or "",
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "read_mins": int(row.read_mins or 3),
        "is_visible": bool(row.is_visible),
        "sort_order": int(row.sort_order or 0),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_admin:
        out["created_at"] = row.created_at.isoformat() if row.created_at else None
    return out


def _unique_slug(db: Session, kind: str, desired: str, *, exclude_id: str | None = None) -> str:
    base = slugify(desired)
    candidate = base
    n = 2
    while True:
        q = select(SiteBlogNewsItem.id).where(
            SiteBlogNewsItem.kind == kind,
            SiteBlogNewsItem.slug == candidate,
        )
        if exclude_id:
            q = q.where(SiteBlogNewsItem.id != exclude_id)
        exists = db.execute(q).scalar_one_or_none()
        if exists is None:
            return candidate
        candidate = f"{base}-{n}"[:180]
        n += 1


def list_items(
    db: Session,
    *,
    kind: str | None = None,
    visible_only: bool = False,
) -> list[SiteBlogNewsItem]:
    ensure_demo_seed(db)
    q = select(SiteBlogNewsItem)
    if kind:
        q = q.where(SiteBlogNewsItem.kind == normalize_kind(kind))
    if visible_only:
        q = q.where(SiteBlogNewsItem.is_visible.is_(True))
    q = q.order_by(SiteBlogNewsItem.published_at.desc(), SiteBlogNewsItem.sort_order.asc())
    return list(db.execute(q).scalars().all())


def get_by_slug(db: Session, kind: str, slug: str, *, visible_only: bool = True) -> SiteBlogNewsItem:
    ensure_demo_seed(db)
    q = select(SiteBlogNewsItem).where(
        SiteBlogNewsItem.kind == normalize_kind(kind),
        SiteBlogNewsItem.slug == (slug or "").strip(),
    )
    if visible_only:
        q = q.where(SiteBlogNewsItem.is_visible.is_(True))
    row = db.execute(q).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return row


def get_by_id(db: Session, item_id: str) -> SiteBlogNewsItem:
    row = db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.id == item_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return row


def create_item(db: Session, payload: dict[str, Any]) -> SiteBlogNewsItem:
    kind = normalize_kind(str(payload.get("kind") or ""))
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title is required")
    body_mode = normalize_body_mode(payload.get("body_mode"))
    body = payload.get("body") or ""
    if body_mode == "html":
        body = sanitize_html(str(body))
    published = _parse_date(payload.get("published_at"))
    slug_src = (payload.get("slug") or "").strip() or title
    row = SiteBlogNewsItem(
        id=str(uuid.uuid4()),
        kind=kind,
        slug=_unique_slug(db, kind, slug_src),
        title=title[:300],
        excerpt=(payload.get("excerpt") or "")[:5000],
        category=(payload.get("category") or ("Announcement" if kind == KIND_NEWS else "General"))[:80],
        author=(payload.get("author") or "VoxBulk")[:120],
        author_role=(payload.get("author_role") or "")[:160],
        image_url=(payload.get("image_url") or None),
        body_mode=body_mode,
        body=str(body),
        published_at=published,
        read_mins=max(1, int(payload.get("read_mins") or 3)),
        is_visible=bool(payload.get("is_visible", True)),
        sort_order=int(payload.get("sort_order") or 0),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_item(db: Session, item_id: str, payload: dict[str, Any]) -> SiteBlogNewsItem:
    row = get_by_id(db, item_id)
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title is required")
        row.title = title[:300]
    if "slug" in payload and (payload.get("slug") or "").strip():
        row.slug = _unique_slug(db, row.kind, str(payload["slug"]), exclude_id=row.id)
    elif "title" in payload and not (payload.get("slug") or "").strip():
        # Keep existing slug unless explicitly changed; do not auto-rename on edit.
        pass
    if "excerpt" in payload:
        row.excerpt = str(payload.get("excerpt") or "")
    if "category" in payload:
        row.category = str(payload.get("category") or "General")[:80]
    if "author" in payload:
        row.author = str(payload.get("author") or "VoxBulk")[:120]
    if "author_role" in payload:
        row.author_role = str(payload.get("author_role") or "")[:160]
    if "image_url" in payload:
        row.image_url = payload.get("image_url") or None
    if "body_mode" in payload:
        row.body_mode = normalize_body_mode(payload.get("body_mode"))
    if "body" in payload:
        body = str(payload.get("body") or "")
        row.body = sanitize_html(body) if row.body_mode == "html" else body
    if "published_at" in payload:
        row.published_at = _parse_date(payload.get("published_at"))
    if "read_mins" in payload:
        row.read_mins = max(1, int(payload.get("read_mins") or 3))
    if "is_visible" in payload:
        row.is_visible = bool(payload.get("is_visible"))
    if "sort_order" in payload:
        row.sort_order = int(payload.get("sort_order") or 0)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def toggle_visible(db: Session, item_id: str) -> SiteBlogNewsItem:
    row = get_by_id(db, item_id)
    row.is_visible = not bool(row.is_visible)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_item(db: Session, item_id: str) -> None:
    row = get_by_id(db, item_id)
    db.delete(row)
    db.commit()


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="published_at must be YYYY-MM-DD",
            ) from exc
    return date.today()


def _blocks_to_html(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        t = block.get("type")
        if t == "h2":
            parts.append(f"<h2>{html.escape(str(block.get('text') or ''))}</h2>")
        elif t == "quote":
            cite = block.get("cite")
            cite_html = f"<cite>— {html.escape(str(cite))}</cite>" if cite else ""
            parts.append(
                f"<blockquote><p>{html.escape(str(block.get('text') or ''))}</p>{cite_html}</blockquote>"
            )
        elif t == "list":
            items = block.get("items") or []
            lis = "".join(f"<li>{html.escape(str(it))}</li>" for it in items)
            parts.append(f"<ul>{lis}</ul>")
        else:
            parts.append(f"<p>{html.escape(str(block.get('text') or ''))}</p>")
    return "\n".join(parts)


def ensure_demo_seed(db: Session) -> None:
    """Insert demo journal/news once when the table is empty."""
    count = db.execute(select(func.count()).select_from(SiteBlogNewsItem)).scalar_one()
    if int(count or 0) > 0:
        return

    blog_seed = _demo_blog_rows()
    news_seed = _demo_news_rows()
    now = datetime.utcnow()
    for i, raw in enumerate(blog_seed + news_seed):
        db.add(
            SiteBlogNewsItem(
                id=str(uuid.uuid4()),
                kind=raw["kind"],
                slug=raw["slug"],
                title=raw["title"],
                excerpt=raw.get("excerpt") or "",
                category=raw.get("category") or "General",
                author=raw.get("author") or "VoxBulk",
                author_role=raw.get("author_role") or "",
                image_url=None,
                body_mode=raw.get("body_mode") or "html",
                body=raw.get("body") or "",
                published_at=raw["published_at"],
                read_mins=int(raw.get("read_mins") or 3),
                is_visible=True,
                sort_order=i,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def _demo_blog_rows() -> list[dict[str, Any]]:
    posts = [
        {
            "slug": "the-real-cost-of-slow-hiring",
            "title": "The real cost of slow hiring — and how to reclaim two weeks per role",
            "excerpt": (
                "Every extra day a role sits open is a day of lost output, stretched teams and a shrinking "
                "candidate pool. Here's how automation flips the maths."
            ),
            "category": "Recruitment",
            "author": "Alex Rahman",
            "author_role": "Head of Product, VoxBulk",
            "published_at": date(2026, 7, 14),
            "read_mins": 6,
            "content": [
                {
                    "type": "p",
                    "text": (
                        "Hiring managers rarely talk about time-to-hire in pounds — but they should. "
                        "A vacant role in a professional services firm costs, on average, £312 per day in "
                        "unrealised revenue. Multiply that by 42 days (the UK median) and every open seat is "
                        "quietly draining more than £13,000 before anyone is even offered the job."
                    ),
                },
                {"type": "h2", "text": "Where the days actually disappear"},
                {
                    "type": "p",
                    "text": (
                        "In the hundreds of pipelines we've audited with clients, the pattern is consistent. "
                        "It's not the interview stage — it's everything around it."
                    ),
                },
                {
                    "type": "list",
                    "items": [
                        "3–5 days lost to CV triage after posting",
                        "4–7 days waiting for candidates to reply to first outreach",
                        "2–4 days per interview slot juggled across three calendars",
                        "1–2 days for hiring managers to write and align on feedback",
                    ],
                },
                {
                    "type": "quote",
                    "text": "We didn't have a candidate problem. We had a coordination problem.",
                    "cite": "Head of Talent, mid-market SaaS",
                },
                {"type": "h2", "text": "What automation actually replaces"},
                {
                    "type": "p",
                    "text": (
                        "Contrary to how it's often sold, AI in recruitment isn't about replacing recruiters — "
                        "it's about deleting the parts of their week they don't want anyway. Screening every "
                        "applicant. Chasing replies. Booking, rebooking, and rebooking again."
                    ),
                },
                {
                    "type": "p",
                    "text": (
                        "When our customers switch on VoxBulk for a role, the same pipeline that took 42 days "
                        "routinely closes in 18. Not because the AI is faster in isolation, but because the "
                        "queue between each human step evaporates."
                    ),
                },
                {"type": "h2", "text": "The two-week rule"},
                {
                    "type": "p",
                    "text": (
                        "If you can shave two weeks off time-to-hire on your ten most active roles, that's "
                        "~£40,000 back into the business per quarter — before you count the retention "
                        "benefits of candidates who don't ghost you halfway through."
                    ),
                },
            ],
        },
        {
            "slug": "whatsapp-beats-email-for-surveys",
            "title": "Why WhatsApp quietly became the highest-signal survey channel",
            "excerpt": (
                "98% open rates aren't a marketing line — they're a structural fact of how people use their "
                "phones in 2026. Here's what that means for feedback programs."
            ),
            "category": "Surveys",
            "author": "Priya Menon",
            "author_role": "Research Lead, VoxBulk",
            "published_at": date(2026, 6, 28),
            "read_mins": 5,
            "content": [
                {
                    "type": "p",
                    "text": (
                        "Email surveys have been dying slowly for a decade. WhatsApp didn't kill them — inbox "
                        "overload did. But WhatsApp is what took their place, and the numbers aren't close."
                    ),
                },
                {"type": "h2", "text": "Open rate isn't a vanity metric"},
                {
                    "type": "p",
                    "text": (
                        "In 2025 benchmarks across 14 industries, WhatsApp surveys hit a median 98% open rate "
                        "and 62% completion. Email? 21% and 4%. The gap widens further outside English-first markets."
                    ),
                },
                {
                    "type": "list",
                    "items": [
                        "Delivered read receipts within 3 minutes on average",
                        "Voice-note replies unlock unfiltered qualitative data",
                        "Native translation means one survey works in 50+ languages",
                    ],
                },
                {
                    "type": "quote",
                    "text": "The customers who never emailed us back left us six-minute voice notes.",
                },
                {"type": "h2", "text": "Designing for the channel, not against it"},
                {
                    "type": "p",
                    "text": (
                        "The mistake most brands make is porting a 20-question web survey straight into "
                        "WhatsApp. Don't. Keep it to five questions, allow voice, and let the AI do the "
                        "translation and sentiment work behind the scenes."
                    ),
                },
            ],
        },
        {
            "slug": "ai-interviews-without-the-bias",
            "title": "AI interviews without the bias — what actually works",
            "excerpt": (
                "Structured scoring, transparent rubrics, and audit trails: three non-negotiables for using "
                "AI in candidate assessment responsibly."
            ),
            "category": "AI & Ethics",
            "author": "Dr. Rania Osei",
            "author_role": "Advisor, VoxBulk",
            "published_at": date(2026, 6, 10),
            "read_mins": 7,
            "content": [
                {
                    "type": "p",
                    "text": (
                        "The concern isn't whether AI can interview candidates. It can, and it does — millions "
                        "of times a month across the market. The concern is whether it does so more fairly than "
                        "the human process it replaces. The honest answer is: only if you design for it."
                    ),
                },
                {"type": "h2", "text": "The three-rubric rule"},
                {
                    "type": "list",
                    "items": [
                        "Every question maps to a competency, not a personality trait",
                        "Every score is explainable in plain English on the report",
                        "Every candidate can request the transcript and rating rationale",
                    ],
                },
                {
                    "type": "quote",
                    "text": "If your AI can't explain why it scored someone a 6, it shouldn't be scoring.",
                },
            ],
        },
        {
            "slug": "multilingual-feedback-global-brands",
            "title": "Multilingual feedback: what global brands get right",
            "excerpt": (
                "When a customer sends a voice note in Arabic and your team reads it in English within "
                "seconds, the loop closes. Here's how leading brands set that up."
            ),
            "category": "Customer Feedback",
            "author": "Marc Lefevre",
            "author_role": "Customer Success, VoxBulk",
            "published_at": date(2026, 5, 22),
            "read_mins": 4,
            "content": [
                {
                    "type": "p",
                    "text": (
                        "There's a persistent myth that global CX programs require regional call centres and "
                        "localised survey teams. In 2026, that's simply no longer true — and it hasn't been "
                        "for eighteen months."
                    ),
                },
                {"type": "h2", "text": "One inbox, every language"},
                {
                    "type": "p",
                    "text": (
                        "The pattern that works: single QR code on the receipt or table tent, WhatsApp opens "
                        "in the customer's default language, voice or text reply accepted, AI translates and "
                        "tags sentiment before it hits your dashboard. The brand team reads one language. The "
                        "customer never switched theirs."
                    ),
                },
            ],
        },
        {
            "slug": "recruitment-automation-regulated-industries",
            "title": "Recruitment automation in regulated industries: a practical guide",
            "excerpt": (
                "Financial services, healthcare, and legal all have hard constraints. That doesn't mean "
                "automation is off the table — it means the guardrails matter more."
            ),
            "category": "Recruitment",
            "author": "Alex Rahman",
            "author_role": "Head of Product, VoxBulk",
            "published_at": date(2026, 5, 3),
            "read_mins": 8,
            "content": [
                {
                    "type": "p",
                    "text": (
                        "Every conversation with a regulated-industry buyer starts the same way: 'We love this, "
                        "but compliance will kill it.' They don't. Not if you bring compliance in on day one."
                    ),
                },
                {"type": "h2", "text": "What compliance actually wants"},
                {
                    "type": "list",
                    "items": [
                        "Data residency guarantees (UK/EU-only processing)",
                        "Full audit trail of every AI decision and prompt",
                        "Human-in-the-loop for any reject decision",
                        "DPA signed before pilot, not after",
                    ],
                },
            ],
        },
    ]
    rows: list[dict[str, Any]] = []
    for p in posts:
        rows.append(
            {
                "kind": KIND_BLOG,
                "slug": p["slug"],
                "title": p["title"],
                "excerpt": p["excerpt"],
                "category": p["category"],
                "author": p["author"],
                "author_role": p["author_role"],
                "published_at": p["published_at"],
                "read_mins": p["read_mins"],
                "body_mode": "html",
                "body": _blocks_to_html(p["content"]),
            }
        )
    return rows


def _demo_news_rows() -> list[dict[str, Any]]:
    items = [
        (
            "multilingual-voice-notes-62-languages",
            date(2026, 7, 15),
            "VoxBulk expands multilingual voice-note support to 62 languages",
            "Customers on the Growth and Scale plans can now receive and translate voice replies in an "
            "additional 12 languages, including Amharic, Sinhala and Uzbek.",
        ),
        (
            "bullhorn-ats-integration",
            date(2026, 7, 2),
            "New Bullhorn ATS integration goes live",
            "Recruitment Automation customers can now push AI interview scores and shortlists directly into "
            "Bullhorn pipelines without middleware.",
        ),
        (
            "soc2-type-ii-renewed",
            date(2026, 6, 24),
            "SOC 2 Type II attestation renewed for a second consecutive year",
            "VoxBulk's controls across security, availability and confidentiality were re-attested by an "
            "independent auditor with zero exceptions.",
        ),
        (
            "ai-calling-survey-exits-beta",
            date(2026, 6, 11),
            "AI Calling Survey exits beta",
            "The fully-automated voice survey product, previously in closed beta with 40 customers, is now "
            "available on the Scale and Enterprise plans.",
        ),
        (
            "cronofy-scheduling-coverage",
            date(2026, 5, 30),
            "Partnership with Cronofy deepens scheduling coverage",
            "Round-robin and pooled availability are now supported natively for teams of up to 200 "
            "interviewers on the Enterprise plan.",
        ),
        (
            "manchester-office-opens",
            date(2026, 5, 8),
            "New office opens in Manchester",
            "The customer success and implementation team expands to a second UK location to support growing "
            "demand across the North of England.",
        ),
        (
            "customer-feedback-benchmarks-report",
            date(2026, 4, 19),
            "Customer feedback benchmarks report published",
            "Our first annual report on WhatsApp feedback benchmarks — covering 14 industries and 3.2M "
            "conversations — is now available on request.",
        ),
        (
            "uk-ai-safety-coalition",
            date(2026, 4, 2),
            "VoxBulk joins the UK AI Safety Coalition",
            "We've formally committed to the coalition's guidelines on AI transparency in candidate "
            "assessment and consumer research.",
        ),
        (
            "arabic-dialect-support",
            date(2026, 3, 21),
            "Arabic dialect support ships across all products",
            "Gulf, Levantine and Egyptian dialects are now handled natively across screening, surveys and "
            "feedback — no configuration required.",
        ),
        (
            "series-a-extension",
            date(2026, 3, 5),
            "Series A extension closed",
            "An extension round brings total funding to £14.2M, led by existing investors and joined by two "
            "new strategic partners in the CX space.",
        ),
    ]
    return [
        {
            "kind": KIND_NEWS,
            "slug": slug,
            "title": title,
            "excerpt": body,
            "category": "Announcement",
            "author": "VoxBulk",
            "author_role": "",
            "published_at": published,
            "read_mins": 1,
            "body_mode": "text",
            "body": body,
        }
        for slug, published, title, body in items
    ]
