"""Public Smart Card QR landing + web session."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.smart_card import SmartCardRepresentative, SmartCardSession
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService
from app.services.smart_card.session_flow_service import SmartCardSessionError, SmartCardSessionFlowService
from app.services.smart_card_public_rate_limit import check_smart_card_rate_limit

router = APIRouter(prefix="/public/smart-card", tags=["public-smart-card"])

_ALLOWED_THEME_IDS = frozenset({"smartcard", "smartcard1", "smartcard2", "smartcard3", "smartcard4"})


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return "unknown"


def _enforce_sc_rate_limit(*, scope: str, identity: str, limit: int, window_sec: int = 60) -> None:
    decision = check_smart_card_rate_limit(
        scope=scope, identity=identity, limit=limit, window_sec=window_sec
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(decision.retry_after_sec)},
        )


def _allowed_public_origins() -> set[str]:
    settings = get_settings()
    origins: set[str] = set()
    for raw in (
        getattr(settings, "public_app_origin", None),
        getattr(settings, "PUBLIC_SITE_URL", None),
        "https://voxbulk.com",
        "https://www.voxbulk.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ):
        s = str(raw or "").strip().rstrip("/")
        if s:
            origins.add(s.lower())
    for part in str(getattr(settings, "cors_allow_origins_raw", "") or "").split(","):
        s = part.strip().rstrip("/")
        if s:
            origins.add(s.lower())
    try:
        for o in settings.cors_allow_origins:
            s = str(o or "").strip().rstrip("/")
            if s:
                origins.add(s.lower())
    except Exception:
        pass
    return origins


def _origin_allowed(request: Request) -> bool:
    """Allow browser Origin/Referer from public site; reject bare API clients with neither."""
    allowed = _allowed_public_origins()
    origin = str(request.headers.get("origin") or "").strip().rstrip("/").lower()
    if origin and origin in allowed:
        return True
    referer = str(request.headers.get("referer") or "").strip()
    if referer:
        try:
            parsed = urlparse(referer)
            base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/").lower()
            if base in allowed:
                return True
        except Exception:
            pass
    # Same-origin or missing both — fail closed for reveal (blocks naive curl).
    return False


def _resolve_theme_id(brand: dict | None) -> str:
    raw = ""
    if isinstance(brand, dict):
        raw = str(brand.get("theme_id") or brand.get("theme") or "").strip().lower()
    return raw if raw in _ALLOWED_THEME_IDS else "smartcard"


def _media_version_for_path(rel_path: str | None) -> str | None:
    """File mtime for cache-busting photo/logo URLs after replace-in-place uploads."""
    if not rel_path:
        return None
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    abs_path = (root / str(rel_path)).resolve()
    try:
        abs_path.relative_to((root / "data").resolve())
        return str(int(abs_path.stat().st_mtime))
    except (ValueError, OSError):
        return None


def _thumb_image_response(
    abs_path,
    *,
    max_edge: int,
    etag: str,
    allow_cors: bool = False,
):
    """Serve a small WebP thumbnail so public cards stay fast on mobile."""
    from io import BytesIO
    from pathlib import Path

    from fastapi.responses import Response
    from PIL import Image, ImageOps

    path = Path(abs_path)
    edge = max(32, min(int(max_edge or 160), 512))
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            im.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            buf = BytesIO()
            # Prefer WebP for smaller payload; fall back to JPEG if needed.
            try:
                save_im = im.convert("RGB") if im.mode == "RGBA" else im
                # Keep alpha for logos with transparency.
                if im.mode == "RGBA":
                    im.save(buf, format="WEBP", quality=72, method=4)
                else:
                    save_im.save(buf, format="WEBP", quality=72, method=4)
                media = "image/webp"
            except Exception:
                buf = BytesIO()
                im.convert("RGB").save(buf, format="JPEG", quality=78, optimize=True)
                media = "image/jpeg"
            headers = {
                "Cache-Control": "public, max-age=86400, immutable",
                "ETag": f'"{etag}-w{edge}"',
            }
            if allow_cors:
                headers["Access-Control-Allow-Origin"] = "*"
                headers["Cross-Origin-Resource-Policy"] = "cross-origin"
            return Response(content=buf.getvalue(), media_type=media, headers=headers)
    except Exception:
        from fastapi.responses import FileResponse

        suffix = path.suffix.lower()
        media = "image/jpeg"
        if suffix == ".png":
            media = "image/png"
        elif suffix == ".webp":
            media = "image/webp"
        headers = {
            "Cache-Control": "public, max-age=3600",
            "ETag": f'"{etag}"',
        }
        if allow_cors:
            headers["Access-Control-Allow-Origin"] = "*"
            headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return FileResponse(path, media_type=media, headers=headers)


def _get_rep(db: Session, token: str) -> SmartCardRepresentative:
    rep = db.execute(
        select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
    ).scalar_one_or_none()
    if rep is None or str(rep.status or "") != "active":
        raise HTTPException(status_code=404, detail="Smart Card QR not found")
    return rep


def _blocked_card_payload(
    *,
    status: str,
    message: str,
    renew_url: str,
    rep: SmartCardRepresentative,
    company,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": status,
        "message": message,
        "renew_url": renew_url,
        "representative": {"name": rep.name},
        "company": {"name": company.name},
    }


def _build_card_payload(db: Session, *, token: str, rep: SmartCardRepresentative, full: bool) -> dict[str, Any]:
    """full=False: shell (names/photos/theme only). full=True: contact + social + WA."""
    company = SmartCardCompanyService.get_or_create(db, rep.org_id)
    mode = SmartCardEntitlementService.access_mode(db, rep.org_id)
    renew_url = "https://dashboard.voxbulk.com/account/smart-card/packages"

    if mode == "expired":
        return _blocked_card_payload(
            status="expired",
            message=(
                "We're sorry — this Smart Card QR account has expired. "
                "Please ask the company to renew their package."
            ),
            renew_url=renew_url,
            rep=rep,
            company=company,
        )

    if mode == "preview_exhausted":
        return _blocked_card_payload(
            status="preview_exhausted",
            message=(
                "Preview tests are used up (15). "
                "This Smart Card QR will go live after the organisation buys or renews a package."
            ),
            renew_url=renew_url,
            rep=rep,
            company=company,
        )

    brand: dict = {}
    if company.brand_defaults_json:
        try:
            parsed_brand = json.loads(company.brand_defaults_json)
            if isinstance(parsed_brand, dict):
                brand = parsed_brand
        except Exception:
            brand = {}

    extra: dict = {}
    if rep.extra_json:
        try:
            parsed_extra = json.loads(rep.extra_json)
            if isinstance(parsed_extra, dict):
                extra = parsed_extra
        except Exception:
            extra = {}

    job_title = (
        str(extra.get("job_title") or extra.get("title") or extra.get("role") or "").strip() or None
    )

    from app.models.organisation import Organisation

    org = db.get(Organisation, rep.org_id)
    has_logo = bool(org and getattr(org, "logo_storage_key", None))
    photo_v = _media_version_for_path(rep.photo_storage_path)
    logo_v = None
    if has_logo and org is not None:
        from app.services.org_logo_storage_service import resolve_logo_path

        logo_path = resolve_logo_path(str(org.logo_storage_key))
        if logo_path is not None:
            try:
                logo_v = str(int(logo_path.stat().st_mtime))
            except OSError:
                logo_v = str(
                    int(getattr(rep, "updated_at", None).timestamp())
                    if getattr(rep, "updated_at", None)
                    else "1"
                )

    photo_url = None
    if rep.photo_storage_path:
        photo_url = f"/public/smart-card/{token}/photo?w=200"
        if photo_v:
            photo_url = f"{photo_url}&v={photo_v}"
    logo_url = None
    if has_logo:
        logo_url = f"/public/smart-card/{token}/logo?w=128"
        if logo_v:
            logo_url = f"{logo_url}&v={logo_v}"

    tagline = str(company.description or "").strip() or None

    shell = {
        "ok": True,
        "status": mode,
        "shell": True,
        "preview_tests_remaining": max(0, 15 - int(company.preview_tests_used or 0))
        if mode == "preview"
        else None,
        "company": {
            "name": company.name,
            "tagline": tagline,
            "logo_url": logo_url,
            "logo_tone": (getattr(org, "logo_tone", None) or None) if org else None,
        },
        "representative": {
            "id": rep.id,
            "name": rep.name,
            "job_title": job_title,
            "photo_url": photo_url,
        },
        "theme_id": _resolve_theme_id(brand),
        "qr_token": rep.qr_token,
    }
    if not full:
        return shell

    from urllib.parse import quote

    from app.services.connection.config_resolver import whatsapp_route_whatsapp_from
    from app.services.connection.constants import SERVICE_CUSTOMER_FEEDBACK, SERVICE_SMART_CARD
    from app.services.smart_card.whatsapp_service import build_smart_card_wa_trigger

    wa_phone = (
        whatsapp_route_whatsapp_from(db, org_id=rep.org_id, service_code=SERVICE_SMART_CARD)
        or whatsapp_route_whatsapp_from(db, org_id=rep.org_id, service_code=SERVICE_CUSTOMER_FEEDBACK)
        or ""
    )
    if not wa_phone:
        try:
            from app.services.customer_feedback.feedback_wa_phone import resolve_feedback_wa_phone_for_qr

            wa_phone = resolve_feedback_wa_phone_for_qr(db, "gb", org_id=rep.org_id) or ""
        except Exception:
            wa_phone = ""

    wa_digits = "".join(c for c in wa_phone if c.isdigit())
    trigger = build_smart_card_wa_trigger(rep_name=rep.name, qr_token=rep.qr_token)
    wa_url = f"https://wa.me/{wa_digits}?text={quote(trigger)}" if wa_digits else None

    social = None
    if rep.social_links_json:
        try:
            social = json.loads(rep.social_links_json)
        except Exception:
            social = None

    rep_address = str(extra.get("address") or "").strip() or None
    rep_location = str(extra.get("location") or "").strip() or None
    brand_address = str(brand.get("address") or brand.get("location") or "").strip() or None
    org_bits = []
    if org is not None:
        for key in ("address_line1", "address_line2", "city", "postcode", "country"):
            val = str(getattr(org, key, None) or "").strip()
            if val:
                org_bits.append(val)
    org_address = ", ".join(org_bits) if org_bits else None
    location = rep_address or rep_location or brand_address or org_address
    location_label = rep_location or (rep_address.split(",")[0].strip() if rep_address else None) or location

    return {
        "ok": True,
        "status": mode,
        "shell": False,
        "preview_tests_remaining": shell["preview_tests_remaining"],
        "company": {
            "name": company.name,
            "website": company.website,
            "description": company.description,
            "tagline": tagline,
            "location": location,
            "location_label": location_label,
            "address": location,
            "logo_url": logo_url,
            "logo_tone": (getattr(org, "logo_tone", None) or None) if org else None,
        },
        "representative": {
            "id": rep.id,
            "name": rep.name,
            "email": rep.email,
            "website": rep.website,
            "mobile": rep.mobile,
            "landline": rep.landline,
            "extension": rep.extension,
            "job_title": job_title,
            "location": rep_location,
            "address": rep_address,
            "social_links": social,
            "photo_url": photo_url,
        },
        "theme_id": _resolve_theme_id(brand),
        "qr_token": rep.qr_token,
        "whatsapp_url": wa_url,
        "feedback_whatsapp_url": wa_url,
    }


@router.get("/{token}")
def get_card(token: str, request: Request, db: Session = Depends(get_db)):
    """HTML shell metadata — no phone/email/social/WhatsApp (use POST /reveal)."""
    settings = get_settings()
    ip_limit = int(getattr(settings, "smart_card_public_rate_limit_per_min", 60) or 60)
    _enforce_sc_rate_limit(scope="shell", identity=_client_ip(request), limit=ip_limit, window_sec=60)
    rep = _get_rep(db, token)
    return _build_card_payload(db, token=token, rep=rep, full=False)


@router.post("/{token}/reveal")
def reveal_card(token: str, request: Request, db: Session = Depends(get_db)):
    """Return full card contact fields after origin + rate-limit checks."""
    settings = get_settings()
    ip = _client_ip(request)
    ip_limit = int(getattr(settings, "smart_card_public_rate_limit_per_min", 60) or 60)
    token_limit = int(getattr(settings, "smart_card_reveal_per_token_per_hour", 60) or 60)
    _enforce_sc_rate_limit(scope="reveal-ip", identity=ip, limit=ip_limit, window_sec=60)
    _enforce_sc_rate_limit(
        scope="reveal-token",
        identity=str(token or "")[:80],
        limit=token_limit,
        window_sec=3600,
    )
    if not _origin_allowed(request):
        raise HTTPException(status_code=403, detail="Reveal not allowed from this origin")
    rep = _get_rep(db, token)
    return _build_card_payload(db, token=token, rep=rep, full=True)


@router.get("/{token}/logo")
def get_card_logo(
    token: str,
    w: int = Query(default=128, ge=32, le=512),
    db: Session = Depends(get_db),
):
    from app.models.organisation import Organisation
    from app.services.org_logo_storage_service import resolve_logo_path

    rep = _get_rep(db, token)
    org = db.get(Organisation, rep.org_id)
    storage_key = getattr(org, "logo_storage_key", None) if org else None
    if not storage_key:
        raise HTTPException(status_code=404, detail="Logo not found")
    path = resolve_logo_path(str(storage_key))
    if path is None:
        raise HTTPException(status_code=404, detail="Logo not found")
    try:
        v = str(int(path.stat().st_mtime))
    except OSError:
        v = "0"
    return _thumb_image_response(path, max_edge=w, etag=v, allow_cors=True)


@router.get("/{token}/photo")
def get_card_photo(
    token: str,
    w: int = Query(default=160, ge=32, le=512),
    db: Session = Depends(get_db),
):
    from pathlib import Path

    rep = _get_rep(db, token)
    if not rep.photo_storage_path:
        raise HTTPException(status_code=404, detail="Photo not found")
    root = Path(__file__).resolve().parents[2]
    abs_path = (root / str(rep.photo_storage_path)).resolve()
    try:
        abs_path.relative_to((root / "data").resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Photo not found") from None
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        v = str(int(abs_path.stat().st_mtime))
    except OSError:
        v = "0"
    return _thumb_image_response(abs_path, max_edge=w, etag=v, allow_cors=False)


@router.get("/{token}/qr.png")
def get_card_qr_png(
    token: str,
    s: int = Query(default=512, ge=64, le=2048),
    fg: str | None = Query(default=None),
    bg: str | None = Query(default=None),
    t: str | None = Query(default=None),
    m: str | None = Query(default=None),
    c: str | None = Query(default=None),
    a: str | None = Query(default=None),
    f: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """PNG QR for this card — honours optional style query overrides for live preview."""
    from fastapi.responses import Response

    from app.services.qr_style_render import merge_style_query_overrides, style_kwargs_from_row
    from app.services.smart_card.qr_image_service import render_rep_qr_png

    rep = _get_rep(db, token)
    overrides = merge_style_query_overrides(
        style_kwargs_from_row(rep),
        fg=fg,
        bg=bg,
        t=t,
        m=m,
        c=c,
        a=a,
        f=f,
    )
    png = render_rep_qr_png(rep, size=int(s), **overrides)
    filename = f"smart-card-{token[:40]}.png"
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=300",
        },
    )


@router.post("/{token}/events")
def record_engagement_event(
    token: str,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
):
    """Fire-and-forget public engagement tracking (social, website, save contact, etc.)."""
    from app.services.smart_card.engagement_service import (
        SmartCardEngagementError,
        SmartCardEngagementService,
    )

    _enforce_sc_rate_limit(scope="events", identity=_client_ip(request), limit=40, window_sec=60)
    rep = _get_rep(db, token)
    body = payload or {}
    try:
        SmartCardEngagementService.record(
            db,
            rep=rep,
            event_type=str(body.get("event_type") or body.get("type") or ""),
            lead_id=(str(body.get("lead_id") or "").strip() or None),
            meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
        )
        db.commit()
        return {"ok": True}
    except SmartCardEngagementError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{token}/assets/{asset_id}")
def get_card_asset(
    token: str,
    asset_id: str,
    lead_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Public catalogue download for a scanned Smart Card, with first-open tracking."""
    from fastapi.responses import FileResponse, RedirectResponse

    from app.models.smart_card import SmartCardAsset, SmartCardLead
    from app.services.smart_card.asset_delivery_service import mark_lead_asset_opened
    from app.services.smart_card.asset_storage_service import resolve_storage_abs_path
    from app.services.smart_card.engagement_service import SmartCardEngagementService

    rep = _get_rep(db, token)
    asset = db.execute(
        select(SmartCardAsset).where(
            SmartCardAsset.id == asset_id,
            SmartCardAsset.org_id == rep.org_id,
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if lead_id:
        lead = db.execute(
            select(SmartCardLead).where(
                SmartCardLead.id == str(lead_id).strip(),
                SmartCardLead.representative_id == rep.id,
                SmartCardLead.org_id == rep.org_id,
            )
        ).scalar_one_or_none()
        if lead is not None:
            try:
                if mark_lead_asset_opened(db, lead=lead, asset_id=asset_id):
                    try:
                        SmartCardEngagementService.record(
                            db,
                            rep=rep,
                            event_type="file_open",
                            lead_id=lead.id,
                            meta={"asset_id": asset_id},
                        )
                    except Exception:
                        pass
                    db.commit()
            except Exception:
                db.rollback()
    else:
        # Count anonymous file opens too (no lead context)
        try:
            SmartCardEngagementService.record(
                db,
                rep=rep,
                event_type="file_open",
                meta={"asset_id": asset_id},
            )
            db.commit()
        except Exception:
            db.rollback()

    if asset.external_url:
        return RedirectResponse(asset.external_url)
    abs_path = resolve_storage_abs_path(asset.storage_path)
    if abs_path is None:
        raise HTTPException(status_code=404, detail="Document not available yet")
    media = {
        ".pdf": "application/pdf",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
    }.get(abs_path.suffix.lower())
    return FileResponse(abs_path, filename=abs_path.name, media_type=media)


@router.post("/{token}/start")
def start_session(
    token: str,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
):
    _enforce_sc_rate_limit(scope="start", identity=_client_ip(request), limit=30, window_sec=60)
    rep = _get_rep(db, token)
    payload = payload or {}
    try:
        result = SmartCardSessionFlowService.start_session(
            db,
            rep=rep,
            channel="web",
            visitor_phone=(str(payload.get("mobile") or "").strip() or None),
            visitor_email=(str(payload.get("email") or "").strip() or None),
            name=(str(payload.get("name") or "").strip() or None),
            company_name=(str(payload.get("company") or "").strip() or None),
        )
        db.commit()
        return result
    except SmartCardSessionError as e:
        code = str(e)
        if code in {"expired", "preview_exhausted"}:
            raise HTTPException(status_code=403, detail=code) from e
        raise HTTPException(status_code=400, detail=code) from e


@router.post("/{token}/answer")
def answer_session(token: str, request: Request, payload: dict, db: Session = Depends(get_db)):
    _enforce_sc_rate_limit(scope="answer", identity=_client_ip(request), limit=30, window_sec=60)
    rep = _get_rep(db, token)
    session_id = str((payload or {}).get("session_id") or "").strip()
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = SmartCardSessionFlowService.advance(
            db,
            session=session,
            answer=str((payload or {}).get("answer") or ""),
            answer_source=str((payload or {}).get("answer_source") or "text"),
        )
        db.commit()
        return result
    except SmartCardSessionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{token}/sessions/{session_id}/back")
def step_back(token: str, session_id: str, db: Session = Depends(get_db)):
    """Rewind one question without losing the scanned business card or typed contact details."""
    rep = _get_rep(db, token)
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = SmartCardSessionFlowService.go_back(db, session=session)
        db.commit()
        return result
    except SmartCardSessionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{token}/card")
async def upload_card(
    token: str,
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    rep = _get_rep(db, token)
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    extracted: dict = {"name": None, "company": None, "email": None, "phone": None}
    card_path: str | None = None
    try:
        from app.services.expo.business_card_ocr_service import ExpoBusinessCardService

        extracted, card_path = ExpoBusinessCardService.save_from_bytes(
            db,
            org_id=str(rep.org_id),
            booth_id=str(rep.id),
            image_bytes=raw,
            content_type=file.content_type or "image/jpeg",
        )
        extracted = extracted or {"name": None, "company": None, "email": None, "phone": None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR unavailable: {e}") from e

    result = SmartCardSessionFlowService.apply_card_ocr(
        db,
        session=session,
        name=(extracted or {}).get("name"),
        company=(extracted or {}).get("company"),
        email=(extracted or {}).get("email"),
        phone=(extracted or {}).get("phone"),
        business_card_path=card_path,
    )
    db.commit()
    return result


@router.post("/{token}/sessions/{session_id}/voice")
async def upload_voice_answer(
    token: str,
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Web voice note — store original audio, STT for answer text, advance session."""
    from app.services.smart_card.voice_note_service import process_web_voice_bytes

    rep = _get_rep(db, token)
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "active":
        return {"ok": True, "done": True, "message": "Thank you"}

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    voice = process_web_voice_bytes(
        db,
        session=session,
        audio_bytes=raw,
        filename=file.filename or "voice.webm",
        content_type=str(file.content_type or "audio/webm"),
    )
    if not voice.get("ok"):
        raise HTTPException(
            status_code=400,
            detail="Sorry — I couldn't hear that clearly. Please type your answer, or record again.",
        )

    session = db.get(SmartCardSession, session_id) or session
    try:
        result = SmartCardSessionFlowService.advance(
            db,
            session=session,
            answer=str(voice.get("answer_text_en") or voice.get("original_text") or ""),
            answer_source="voice",
            original_text=str(voice.get("original_text") or "") or None,
            answer_text_en=str(voice.get("answer_text_en") or "") or None,
            voice_job_id=str(voice.get("job_id") or "") or None,
        )
        db.commit()
    except SmartCardSessionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    result["original_text"] = voice.get("original_text")
    result["answer_text_en"] = voice.get("answer_text_en")
    result["voice_job_id"] = voice.get("job_id")
    return result
