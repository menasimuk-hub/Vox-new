from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.admin_rbac import get_active_admin_user, resolve_admin_role
from app.models.admin_user import AdminUser
from app.models.branch import Branch
from app.models.organisation import Organisation
from app.models.support_ticket import (
    CannedReply,
    CannedReplyCategory,
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketEvent,
    SupportTicketMessage,
)
from app.models.user import User


CATEGORIES = {"technical", "invoices", "pre-sale", "smart_card"}
STATUSES = {"open", "pending", "waiting", "resolved", "closed"}
CHANNELS = {"email", "web", "imap", "assistant"}
OPEN_QUEUE_STATUSES = {"open", "pending", "waiting"}
PRIORITIES = {"urgent", "high", "normal", "low"}


def normalize_category(category: str) -> str:
    c = (category or "").strip().lower().replace("_", "-")
    if c in {"invoice", "billing", "finance"}:
        c = "invoices"
    if c in {"presale", "pre_sale", "sales"}:
        c = "pre-sale"
    if c in {"smart-card", "smartcard", "smart-card-qr"}:
        c = "smart_card"
    if c not in CATEGORIES:
        raise ValueError("category must be one of: technical, invoices, pre-sale, smart_card")
    return c


def normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s not in STATUSES:
        raise ValueError("status must be one of: open, pending, waiting, resolved, closed")
    return s


def normalize_channel(channel: str | None) -> str:
    c = (channel or "web").strip().lower()
    if c in {"mail", "smtp"}:
        c = "email"
    if c not in CHANNELS:
        raise ValueError("channel must be one of: email, web, imap, assistant")
    return c


def normalize_priority(priority: str | None) -> str | None:
    if priority is None or not str(priority).strip():
        return None
    p = str(priority).strip().lower()
    if p not in PRIORITIES:
        raise ValueError("priority must be one of: urgent, high, normal, low")
    return p


def support_visible_categories(role: str) -> set[str] | None:
    r = (role or "").strip().lower()
    if r in {"superadmin", "admin"}:
        return None
    if r == "accountant":
        return {"invoices"}
    if r in {"technical", "support", "technical/support"}:
        return {"technical", "smart_card"}
    if r == "marketing":
        return {"pre-sale"}
    return set()


def admin_can_access_ticket(role: str, ticket: SupportTicket) -> bool:
    cats = support_visible_categories(role)
    return cats is None or ticket.category in cats


class SupportTicketService:
    @staticmethod
    def create_ticket(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        category: str,
        subject: str,
        message: str,
        branch_id: str | None = None,
        priority: str | None = None,
        channel: str | None = "web",
        attachments: list[dict] | None = None,
        staff_note: str | None = None,
    ) -> SupportTicket:
        cat = normalize_category(category)
        if branch_id:
            ok = db.execute(select(Branch.id).where(Branch.id == branch_id, Branch.org_id == org_id)).scalar_one_or_none()
            if ok is None:
                raise ValueError("Invalid branch for organisation")
        now = datetime.utcnow()
        t = SupportTicket(
            organisation_id=org_id,
            branch_id=branch_id,
            created_by_user_id=user_id,
            category=cat,
            subject=(subject or "").strip(),
            status="open",
            priority=normalize_priority(priority) or "normal",
            channel=normalize_channel(channel),
            customer_unread=False,
            admin_unread=True,
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(t)
        db.flush()
        t.public_ref = f"TKT-{t.id:06d}"
        m = SupportTicketMessage(
            ticket_id=t.id,
            sender_type="customer",
            sender_user_id=user_id,
            body=(message or "").strip(),
            is_internal_note=False,
            created_at=now,
        )
        db.add(m)
        db.flush()
        SupportTicketService._add_attachments(db, ticket_id=t.id, message_id=m.id, attachments=attachments or [])
        note = (staff_note or "").strip()
        if note:
            db.add(
                SupportTicketMessage(
                    ticket_id=t.id,
                    sender_type="system",
                    sender_user_id=None,
                    body=note[:8000],
                    is_internal_note=True,
                    created_at=now,
                )
            )
        SupportTicketService._event(db, t, "created", "customer", actor_user_id=user_id)
        db.commit()
        db.refresh(t)
        try:
            from app.services.support_ticket_email_service import SupportTicketEmailService

            SupportTicketEmailService.notify_created(db, t)
        except Exception:
            pass
        return t

    @staticmethod
    def list_customer_tickets(db: Session, *, org_id: str, user_id: str, status: str | None = None, limit: int = 50, offset: int = 0):
        stmt = select(SupportTicket).where(SupportTicket.organisation_id == org_id, SupportTicket.created_by_user_id == user_id)
        if status:
            stmt = stmt.where(SupportTicket.status == normalize_status(status))
        return list(db.execute(stmt.order_by(SupportTicket.last_message_at.desc()).limit(min(max(limit, 1), 100)).offset(max(offset, 0))).scalars())

    @staticmethod
    def get_customer_ticket(db: Session, *, org_id: str, user_id: str, ticket_id: int) -> SupportTicket | None:
        return db.execute(
            select(SupportTicket).where(
                SupportTicket.id == ticket_id,
                SupportTicket.organisation_id == org_id,
                SupportTicket.created_by_user_id == user_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def customer_reply(db: Session, *, ticket: SupportTicket, user_id: str, message: str, attachments: list[dict] | None = None) -> SupportTicket:
        now = datetime.utcnow()
        old_status = ticket.status
        if ticket.status == "closed":
            ticket.status = "open"
            ticket.closed_at = None
            SupportTicketService._event(db, ticket, "reopened", "customer", actor_user_id=user_id, from_value=old_status, to_value="open")
        ticket.customer_unread = False
        ticket.admin_unread = True
        ticket.last_message_at = now
        ticket.updated_at = now
        db.add(ticket)
        m = SupportTicketMessage(ticket_id=ticket.id, sender_type="customer", sender_user_id=user_id, body=message.strip(), created_at=now)
        db.add(m)
        db.flush()
        SupportTicketService._add_attachments(db, ticket_id=ticket.id, message_id=m.id, attachments=attachments or [])
        db.commit()
        db.refresh(ticket)
        return ticket

    @staticmethod
    def list_admin_tickets(
        db: Session,
        *,
        role: str,
        status: str | None = None,
        category: str | None = None,
        assigned_admin_user_id: str | None = None,
        organisation_id: str | None = None,
        search: str | None = None,
        channel: str | None = None,
        priority: str | None = None,
        open_queue: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        stmt = select(SupportTicket)
        allowed = support_visible_categories(role)
        if allowed is not None:
            if not allowed:
                return []
            stmt = stmt.where(SupportTicket.category.in_(allowed))
        if open_queue:
            stmt = stmt.where(SupportTicket.status.in_(tuple(OPEN_QUEUE_STATUSES)))
        elif status:
            # Allow comma-separated statuses
            parts = [normalize_status(p) for p in str(status).split(",") if p.strip()]
            if len(parts) == 1:
                stmt = stmt.where(SupportTicket.status == parts[0])
            elif parts:
                stmt = stmt.where(SupportTicket.status.in_(parts))
        if category:
            stmt = stmt.where(SupportTicket.category == normalize_category(category))
        if channel:
            stmt = stmt.where(SupportTicket.channel == normalize_channel(channel))
        if priority:
            stmt = stmt.where(SupportTicket.priority == normalize_priority(priority))
        if assigned_admin_user_id:
            if assigned_admin_user_id == "unassigned":
                stmt = stmt.where(SupportTicket.assigned_admin_user_id.is_(None))
            else:
                stmt = stmt.where(SupportTicket.assigned_admin_user_id == assigned_admin_user_id)
        if organisation_id:
            stmt = stmt.where(SupportTicket.organisation_id == organisation_id)
        if search:
            q = f"%{search.strip()}%"
            creator_ids = list(
                db.execute(select(User.id).where(User.email.ilike(q)).limit(50)).scalars()
            )
            clauses = [SupportTicket.public_ref.ilike(q), SupportTicket.subject.ilike(q)]
            if creator_ids:
                clauses.append(SupportTicket.created_by_user_id.in_(creator_ids))
            stmt = stmt.where(or_(*clauses))
        return list(db.execute(stmt.order_by(SupportTicket.last_message_at.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0))).scalars())

    @staticmethod
    def get_admin_ticket(db: Session, *, role: str, ticket_id: int) -> SupportTicket | None:
        t = db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id)).scalar_one_or_none()
        if t is None or not admin_can_access_ticket(role, t):
            return None
        return t

    @staticmethod
    def admin_reply(db: Session, *, ticket: SupportTicket, admin_user: User, message: str, internal: bool = False, attachments: list[dict] | None = None) -> SupportTicket:
        now = datetime.utcnow()
        au = get_active_admin_user(db, admin_user)
        ticket.admin_unread = False
        if not internal:
            ticket.customer_unread = True
            ticket.last_message_at = now
        ticket.updated_at = now
        if ticket.status == "open":
            ticket.status = "pending"
        db.add(ticket)
        m = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_type="admin",
            sender_user_id=admin_user.id,
            sender_admin_user_id=au.id if au else None,
            body=message.strip(),
            is_internal_note=bool(internal),
            created_at=now,
        )
        db.add(m)
        db.flush()
        SupportTicketService._add_attachments(db, ticket_id=ticket.id, message_id=m.id, attachments=attachments or [])
        if not internal:
            from app.services.notification_service import NotificationService

            NotificationService.create_ticket_reply_notification(db, ticket=ticket)
        db.commit()
        db.refresh(ticket)
        if not internal:
            try:
                from app.services.support_ticket_email_service import SupportTicketEmailService

                SupportTicketEmailService.notify_reply(db, ticket, reply_body=message.strip())
            except Exception:
                pass
        return ticket

    @staticmethod
    def set_status(db: Session, *, ticket: SupportTicket, status: str, actor: User) -> SupportTicket:
        next_status = normalize_status(status)
        old = ticket.status
        now = datetime.utcnow()
        ticket.status = next_status
        ticket.closed_at = now if next_status in {"closed", "resolved"} else None
        ticket.updated_at = now
        db.add(ticket)
        SupportTicketService._event(db, ticket, "status_changed", "admin", actor_user_id=actor.id, from_value=old, to_value=next_status)
        db.commit()
        db.refresh(ticket)
        try:
            from app.services.support_ticket_email_service import SupportTicketEmailService

            SupportTicketEmailService.notify_status(db, ticket)
        except Exception:
            pass
        return ticket

    @staticmethod
    def assign(db: Session, *, ticket: SupportTicket, admin_id: str | None, actor: User) -> SupportTicket:
        old = ticket.assigned_admin_user_id
        if admin_id:
            au = db.execute(select(AdminUser).where(AdminUser.id == admin_id, AdminUser.is_active == True)).scalar_one_or_none()  # noqa: E712
            if au is None:
                raise ValueError("Assigned admin not found or inactive")
            role = "superadmin" if au.is_superuser else (au.role or "marketing")
            if not admin_can_access_ticket(role, ticket):
                raise ValueError("Assigned admin role cannot access this ticket category")
        now = datetime.utcnow()
        ticket.assigned_admin_user_id = admin_id or None
        ticket.updated_at = now
        db.add(ticket)
        SupportTicketService._event(db, ticket, "reassigned", "admin", actor_user_id=actor.id, from_value=old, to_value=admin_id)
        db.commit()
        db.refresh(ticket)
        if admin_id:
            try:
                from app.services.support_ticket_email_service import SupportTicketEmailService

                SupportTicketEmailService.notify_assigned(db, ticket)
            except Exception:
                pass
        return ticket

    @staticmethod
    def messages(db: Session, ticket_id: int, *, include_internal: bool = False):
        stmt = select(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket_id)
        if not include_internal:
            stmt = stmt.where(SupportTicketMessage.is_internal_note == False)  # noqa: E712
        return list(db.execute(stmt.order_by(SupportTicketMessage.created_at.asc())).scalars())

    @staticmethod
    def get_attachment(db: Session, attachment_id: int) -> SupportTicketAttachment | None:
        return db.execute(select(SupportTicketAttachment).where(SupportTicketAttachment.id == attachment_id)).scalar_one_or_none()

    @staticmethod
    def close_by_customer(db: Session, *, ticket: SupportTicket, user_id: str) -> SupportTicket:
        old = ticket.status
        now = datetime.utcnow()
        ticket.status = "closed"
        ticket.closed_at = now
        ticket.updated_at = now
        ticket.customer_unread = False
        db.add(ticket)
        SupportTicketService._event(db, ticket, "closed", "customer", actor_user_id=user_id, from_value=old, to_value="closed")
        db.commit()
        db.refresh(ticket)
        return ticket

    @staticmethod
    def _add_attachments(db: Session, *, ticket_id: int, message_id: int, attachments: list[dict]) -> None:
        for a in attachments:
            db.add(
                SupportTicketAttachment(
                    ticket_id=ticket_id,
                    message_id=message_id,
                    filename=str(a["filename"])[:255],
                    content_type=str(a["content_type"])[:120],
                    size_bytes=int(a["size_bytes"]),
                    data=a["data"],
                    created_at=datetime.utcnow(),
                )
            )

    @staticmethod
    def events(db: Session, ticket_id: int):
        return list(db.execute(select(SupportTicketEvent).where(SupportTicketEvent.ticket_id == ticket_id).order_by(SupportTicketEvent.created_at.asc())).scalars())

    @staticmethod
    def kpis(db: Session, *, role: str) -> dict[str, int]:
        stmt = select(SupportTicket)
        allowed = support_visible_categories(role)
        if allowed is not None:
            if not allowed:
                return {k: 0 for k in ["total_open", "total_pending", "total_closed", "unassigned", "technical_open", "invoices_open", "pre_sale_open", "overdue"]}
            stmt = stmt.where(SupportTicket.category.in_(allowed))
        rows = list(db.execute(stmt).scalars())
        overdue_cutoff = datetime.utcnow() - timedelta(days=2)
        return {
            "total_open": sum(1 for t in rows if t.status == "open"),
            "total_pending": sum(1 for t in rows if t.status == "pending"),
            "total_waiting": sum(1 for t in rows if t.status == "waiting"),
            "total_resolved": sum(1 for t in rows if t.status == "resolved"),
            "total_closed": sum(1 for t in rows if t.status == "closed"),
            "open_queue": sum(1 for t in rows if t.status in OPEN_QUEUE_STATUSES),
            "admin_unread": sum(1 for t in rows if t.admin_unread),
            "unassigned": sum(1 for t in rows if t.assigned_admin_user_id is None and t.status not in {"closed", "resolved"}),
            "technical_open": sum(1 for t in rows if t.category == "technical" and t.status == "open"),
            "invoices_open": sum(1 for t in rows if t.category == "invoices" and t.status == "open"),
            "pre_sale_open": sum(1 for t in rows if t.category == "pre-sale" and t.status == "open"),
            "overdue": sum(1 for t in rows if t.status not in {"closed", "resolved"} and t.last_message_at < overdue_cutoff),
        }

    @staticmethod
    def _event(db: Session, ticket: SupportTicket, event_type: str, actor_type: str, *, actor_user_id: str | None = None, actor_admin_user_id: str | None = None, from_value: str | None = None, to_value: str | None = None):
        db.add(
            SupportTicketEvent(
                ticket_id=ticket.id,
                event_type=event_type,
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                actor_admin_user_id=actor_admin_user_id,
                from_value=from_value,
                to_value=to_value,
                created_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def insights(db: Session, *, role: str) -> dict:
        from collections import defaultdict

        stmt = select(SupportTicket)
        allowed = support_visible_categories(role)
        if allowed is not None:
            if not allowed:
                return {
                    "kpis": {"avg_first_reply": "—", "avg_resolution": "—", "tickets_this_week": 0, "csat": "—"},
                    "volume_trend": [],
                    "response_trend": [],
                    "csat_trend": [],
                    "agents": [],
                }
            stmt = stmt.where(SupportTicket.category.in_(allowed))
        rows = list(db.execute(stmt).scalars())
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        tickets_this_week = sum(1 for t in rows if t.created_at and t.created_at >= week_ago)

        # First admin reply ages
        first_reply_hours: list[float] = []
        resolution_hours: list[float] = []
        for t in rows:
            msgs = SupportTicketService.messages(db, t.id, include_internal=False)
            first_admin = next((m for m in msgs if m.sender_type == "admin"), None)
            if first_admin and t.created_at:
                first_reply_hours.append(max(0.0, (first_admin.created_at - t.created_at).total_seconds() / 3600.0))
            if t.status in {"resolved", "closed"} and t.closed_at and t.created_at:
                resolution_hours.append(max(0.0, (t.closed_at - t.created_at).total_seconds() / 3600.0))

        def _avg_label(vals: list[float]) -> str:
            if not vals:
                return "—"
            avg = sum(vals) / len(vals)
            if avg < 1:
                return f"{int(avg * 60)}m"
            return f"{avg:.1f}h"

        volume_by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"created": 0, "resolved": 0})
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).strftime("%a")
            volume_by_day[day]  # ensure key
        for t in rows:
            if t.created_at and t.created_at >= week_ago:
                volume_by_day[t.created_at.strftime("%a")]["created"] += 1
            if t.closed_at and t.closed_at >= week_ago and t.status in {"resolved", "closed"}:
                volume_by_day[t.closed_at.strftime("%a")]["resolved"] += 1

        agent_stats: dict[str, dict] = defaultdict(lambda: {"resolved": 0, "first_reply_sum": 0.0, "first_reply_n": 0})
        for t in rows:
            if not t.assigned_admin_user_id:
                continue
            email = db.execute(select(AdminUser.email).where(AdminUser.id == t.assigned_admin_user_id)).scalar_one_or_none() or t.assigned_admin_user_id
            if t.status in {"resolved", "closed"}:
                agent_stats[email]["resolved"] += 1
            msgs = SupportTicketService.messages(db, t.id, include_internal=False)
            first_admin = next((m for m in msgs if m.sender_type == "admin"), None)
            if first_admin and t.created_at:
                agent_stats[email]["first_reply_sum"] += max(0.0, (first_admin.created_at - t.created_at).total_seconds() / 3600.0)
                agent_stats[email]["first_reply_n"] += 1

        agents = []
        for email, st in sorted(agent_stats.items(), key=lambda x: -x[1]["resolved"])[:20]:
            fr = "—"
            if st["first_reply_n"]:
                avg = st["first_reply_sum"] / st["first_reply_n"]
                fr = f"{int(avg * 60)}m" if avg < 1 else f"{avg:.1f}h"
            agents.append({"email": email, "resolved": st["resolved"], "first_reply": fr, "csat": "—"})

        day_order = [(now - timedelta(days=i)).strftime("%a") for i in range(6, -1, -1)]
        volume_trend = [{"day": d, **volume_by_day[d]} for d in day_order]

        return {
            "kpis": {
                "avg_first_reply": _avg_label(first_reply_hours),
                "avg_resolution": _avg_label(resolution_hours),
                "tickets_this_week": tickets_this_week,
                "csat": "—",
            },
            "volume_trend": volume_trend,
            "response_trend": [
                {"period": "This week", "first_reply": round(sum(first_reply_hours) / len(first_reply_hours), 2) if first_reply_hours else 0, "resolution": round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else 0}
            ],
            "csat_trend": [],
            "agents": agents,
        }

    @staticmethod
    def sla_breaches(db: Session, *, role: str) -> list[dict]:
        from app.services.support_kb_service import SupportSlaService

        settings = SupportSlaService.get_row(db)
        first_h = int(settings.first_response_hours or 4)
        resolve_h = int(settings.resolve_hours or 48)
        waiting_h = int(settings.waiting_hours or 24)
        now = datetime.utcnow()
        stmt = select(SupportTicket).where(SupportTicket.status.in_(tuple(OPEN_QUEUE_STATUSES)))
        allowed = support_visible_categories(role)
        if allowed is not None:
            if not allowed:
                return []
            stmt = stmt.where(SupportTicket.category.in_(allowed))
        rows = list(db.execute(stmt.order_by(SupportTicket.last_message_at.asc()).limit(200)).scalars())
        out = []
        for t in rows:
            age_h = max(0.0, (now - (t.created_at or now)).total_seconds() / 3600.0)
            idle_h = max(0.0, (now - (t.last_message_at or now)).total_seconds() / 3600.0)
            msgs = SupportTicketService.messages(db, t.id, include_internal=False)
            has_admin = any(m.sender_type == "admin" for m in msgs)
            breached = False
            at_risk = False
            label = "On track"
            if not has_admin and age_h >= first_h:
                breached = True
                label = f"First response overdue ({int(age_h)}h)"
            elif not has_admin and age_h >= first_h * 0.75:
                at_risk = True
                label = "First response at risk"
            elif age_h >= resolve_h:
                breached = True
                label = f"Resolution overdue ({int(age_h)}h)"
            elif t.status == "waiting" and idle_h >= waiting_h:
                breached = True
                label = "Waiting too long"
            elif age_h >= resolve_h * 0.75:
                at_risk = True
                label = "Resolution at risk"
            if not breached and not at_risk:
                continue
            d = ticket_to_dict(db, t)
            d["breached"] = breached
            d["label"] = label
            out.append(d)
        return out

    @staticmethod
    def polish_reply(db: Session, *, draft: str) -> str:
        text = (draft or "").strip()
        if not text:
            return ""
        try:
            from app.services.agents.base import AgentMessage
            from app.services.providers.openai_service import OpenAIProviderService

            result = OpenAIProviderService.complete(
                db,
                system_prompt="You polish customer support replies. Keep meaning, make them clear, professional and concise. Return only the polished reply text.",
                messages=[AgentMessage(role="user", content=text)],
                max_tokens=800,
            )
            polished = str(getattr(result, "assistant_text", None) or "").strip()
            if polished:
                return polished
        except Exception:
            pass
        sentence = text[0].upper() + text[1:] if text else ""
        if sentence and sentence[-1] not in ".!?":
            sentence += "."
        return (
            "Thanks for your patience on this.\n\n"
            + sentence.replace(" cant ", " can't ").replace(" dont ", " don't ")
            + "\n\nIf anything above isn't clear, just reply here and I'll pick it straight back up."
        )


class CannedReplyService:
    @staticmethod
    def list_categories(db: Session):
        return list(db.execute(select(CannedReplyCategory).order_by(CannedReplyCategory.name.asc())).scalars())

    @staticmethod
    def upsert_category(db: Session, *, category_id: int | None, name: str, description: str | None):
        now = datetime.utcnow()
        row = db.get(CannedReplyCategory, category_id) if category_id else None
        if row is None:
            row = CannedReplyCategory(name=name.strip(), description=description, created_at=now, updated_at=now)
        else:
            row.name = name.strip()
            row.description = description
            row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_category(db: Session, category_id: int) -> None:
        db.query(CannedReply).filter(CannedReply.category_id == category_id).update({"category_id": None})
        row = db.get(CannedReplyCategory, category_id)
        if row is not None:
            db.delete(row)
        db.commit()

    @staticmethod
    def list_replies(db: Session, *, search: str | None = None, category_id: int | None = None, active_only: bool = False):
        stmt = select(CannedReply)
        if active_only:
            stmt = stmt.where(CannedReply.is_active == True)  # noqa: E712
        if category_id:
            stmt = stmt.where(CannedReply.category_id == category_id)
        if search:
            q = f"%{search.strip()}%"
            stmt = stmt.where(or_(CannedReply.title.ilike(q), CannedReply.question.ilike(q), CannedReply.answer.ilike(q)))
        return list(db.execute(stmt.order_by(CannedReply.updated_at.desc()).limit(200)).scalars())

    @staticmethod
    def upsert_reply(db: Session, *, reply_id: int | None, category_id: int | None, title: str, question: str, answer: str, is_active: bool):
        now = datetime.utcnow()
        row = db.get(CannedReply, reply_id) if reply_id else None
        if row is None:
            row = CannedReply(created_at=now)
        if category_id and db.get(CannedReplyCategory, category_id) is None:
            raise ValueError("Canned reply category not found")
        row.category_id = category_id
        row.title = title.strip()
        row.question = question.strip()
        row.answer = answer.strip()
        row.is_active = bool(is_active)
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_reply(db: Session, reply_id: int) -> None:
        row = db.get(CannedReply, reply_id)
        if row is not None:
            db.delete(row)
        db.commit()


def ticket_to_dict(db: Session, t: SupportTicket) -> dict:
    org = db.execute(select(Organisation.name).where(Organisation.id == t.organisation_id)).scalar_one_or_none()
    branch = db.execute(select(Branch.name).where(Branch.id == t.branch_id)).scalar_one_or_none() if t.branch_id else None
    creator = db.execute(select(User.email).where(User.id == t.created_by_user_id)).scalar_one_or_none()
    assigned = db.execute(select(AdminUser.email).where(AdminUser.id == t.assigned_admin_user_id)).scalar_one_or_none() if t.assigned_admin_user_id else None
    return {
        "id": t.id,
        "public_ref": t.public_ref or f"TKT-{t.id:06d}",
        "organisation_id": t.organisation_id,
        "organisation_name": org,
        "branch_id": t.branch_id,
        "branch_name": branch,
        "created_by_user_id": t.created_by_user_id,
        "created_by_email": creator,
        "category": t.category,
        "subject": t.subject,
        "status": t.status,
        "priority": t.priority or "normal",
        "channel": getattr(t, "channel", None) or "web",
        "assigned_admin_user_id": t.assigned_admin_user_id,
        "assigned_admin_email": assigned,
        "customer_unread": bool(t.customer_unread),
        "admin_unread": bool(t.admin_unread),
        "last_message_at": t.last_message_at,
        "closed_at": t.closed_at,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def message_to_dict(db: Session, m: SupportTicketMessage) -> dict:
    email = None
    if m.sender_admin_user_id:
        email = db.execute(select(AdminUser.email).where(AdminUser.id == m.sender_admin_user_id)).scalar_one_or_none()
    if email is None and m.sender_user_id:
        email = db.execute(select(User.email).where(User.id == m.sender_user_id)).scalar_one_or_none()
    return {
        "id": m.id,
        "ticket_id": m.ticket_id,
        "sender_type": m.sender_type,
        "sender_user_id": m.sender_user_id,
        "sender_admin_user_id": m.sender_admin_user_id,
        "sender_email": email,
        "body": m.body,
        "is_internal_note": bool(m.is_internal_note),
        "created_at": m.created_at,
        "attachments": [attachment_to_dict(a) for a in db.execute(select(SupportTicketAttachment).where(SupportTicketAttachment.message_id == m.id).order_by(SupportTicketAttachment.created_at.asc())).scalars()],
    }


def attachment_to_dict(a: SupportTicketAttachment) -> dict:
    return {
        "id": a.id,
        "ticket_id": a.ticket_id,
        "message_id": a.message_id,
        "filename": a.filename,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "created_at": a.created_at,
    }


def canned_category_to_dict(c: CannedReplyCategory) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description, "created_at": c.created_at, "updated_at": c.updated_at}


def canned_reply_to_dict(db: Session, r: CannedReply) -> dict:
    name = db.execute(select(CannedReplyCategory.name).where(CannedReplyCategory.id == r.category_id)).scalar_one_or_none() if r.category_id else None
    return {
        "id": r.id,
        "category_id": r.category_id,
        "category_name": name,
        "title": r.title,
        "question": r.question,
        "answer": r.answer,
        "is_active": bool(r.is_active),
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }

