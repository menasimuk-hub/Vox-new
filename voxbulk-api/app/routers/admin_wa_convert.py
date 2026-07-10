"""Admin API — WA Templates Convert (Meta MARKETING → Utility)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateError
from app.services.wa_template_convert_service import (
    get_convert_template,
    list_marketing_for_convert,
    push_convert_template,
    regenerate_convert_template,
    resolve_convert_llm_config,
    save_convert_template,
)

router = APIRouter(prefix="/admin/wa-templates/convert", tags=["admin-wa-convert"])


def _raise(exc: Exception, *, code: int = status.HTTP_400_BAD_REQUEST) -> None:
    detail = getattr(exc, "payload", None) or {"message": str(exc)}
    if isinstance(detail, str):
        detail = {"message": detail}
    raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/marketing")
def convert_list_marketing(
    product: str = Query(default="all"),
    q: str | None = Query(default=None),
    connection_profile_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """List Survey/CF templates Meta marked as MARKETING (actionable local rows preferred)."""
    try:
        return list_marketing_for_convert(
            db,
            product=product,
            q=q,
            connection_profile_id=connection_profile_id,
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc, code=status.HTTP_502_BAD_GATEWAY)


@router.get("/llm")
def convert_llm_status(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "llm": resolve_convert_llm_config(db)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@router.get("/{product}/{template_id}")
def convert_get_template(
    product: str,
    template_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return get_convert_template(db, product=product, template_id=template_id)
    except SurveyWhatsappTemplateError as exc:
        _raise(exc, code=status.HTTP_404_NOT_FOUND)


@router.post("/{product}/{template_id}/regenerate")
def convert_regenerate(
    product: str,
    template_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    try:
        return regenerate_convert_template(
            db,
            product=product,
            template_id=template_id,
            llm_provider=body.get("llm_provider"),
        )
    except SurveyWhatsappTemplateError as exc:
        _raise(exc)
    except ValueError as exc:
        _raise(exc)
    except Exception as exc:  # noqa: BLE001
        _raise(exc, code=status.HTTP_502_BAD_GATEWAY)


@router.post("/{product}/{template_id}/save")
def convert_save(
    product: str,
    template_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    try:
        return save_convert_template(
            db,
            product=product,
            template_id=template_id,
            header=body.get("header"),
            body=body.get("body"),
            footer=body.get("footer"),
            buttons=body.get("buttons"),
        )
    except SurveyWhatsappTemplateError as exc:
        _raise(exc)


@router.post("/{product}/{template_id}/push")
def convert_push(
    product: str,
    template_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """Rename same DB id → push new Utility name → delete old MARKETING name.

    Body: ``{ "targets": "99" | "55" | "all" }``
    """
    body = payload or {}
    targets = str(body.get("targets") or "all").strip().lower()
    if targets not in ("99", "55", "all"):
        raise HTTPException(status_code=400, detail="targets must be 99, 55, or all")
    try:
        return push_convert_template(
            db,
            product=product,
            template_id=template_id,
            targets=targets,  # type: ignore[arg-type]
            force_push=bool(body.get("force_push", True)),
        )
    except SurveyWhatsappTemplateError as exc:
        _raise(exc)
    except Exception as exc:  # noqa: BLE001
        _raise(exc, code=status.HTTP_502_BAD_GATEWAY)
