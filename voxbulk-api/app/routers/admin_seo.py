from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.services import site_seo_service as svc
from app.services.gsc_oauth_service import (
    admin_redirect_origin,
    disconnect_gsc,
    gsc_oauth_complete,
    gsc_oauth_start,
    refresh_gsc_metrics,
)
from app.services.site_blog_news_image import save_uploaded_theme_image

admin_router = APIRouter(prefix="/admin/seo", tags=["admin-seo"])
public_router = APIRouter(prefix="/frontpage", tags=["frontpage-seo"])


class SettingsIn(BaseModel):
    site_name: str | None = None
    title_template: str | None = None
    default_meta_description: str | None = None
    default_social_image_url: str | None = None
    home_title: str | None = None
    home_description: str | None = None
    home_focus_keyword: str | None = None
    home_tags: str | None = None
    schema_organization: bool | None = None
    schema_website: bool | None = None
    schema_breadcrumbs: bool | None = None
    schema_content: bool | None = None
    google_site_verification: str | None = None
    google_analytics_id: str | None = None
    meta_pixel_id: str | None = None
    linkedin_partner_id: str | None = None
    google_ads_id: str | None = None
    x_pixel_id: str | None = None
    tiktok_pixel_id: str | None = None
    pinterest_tag_id: str | None = None
    google_news_enabled: bool | None = None
    google_news_publication: str | None = None
    google_news_language: str | None = None
    gsc_property_url: str | None = None
    robots_txt: str | None = None
    psi_api_key: str | None = None
    moz_access_id: str | None = None
    moz_secret_key: str | None = None


class ContentSeoIn(BaseModel):
    slug: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    robots: str | None = None
    focus_keyword: str | None = None
    tags: str | None = None
    author: str | None = None
    published_at: str | None = None
    social_title: str | None = None
    social_description: str | None = None
    social_image_url: str | None = None


class RedirectIn(BaseModel):
    from_path: str
    to_path: str
    status_code: int = 301


class PsiConnectIn(BaseModel):
    api_key: str = Field(min_length=1)


class MozConnectIn(BaseModel):
    access_id: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)


class MarkFixedIn(BaseModel):
    url: str


class RobotsIn(BaseModel):
    robots_txt: str


@admin_router.get("/overview")
def admin_overview(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.overview(db)


@admin_router.get("/content/{kind}")
def admin_list_content(kind: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return {"items": svc.list_content(db, kind)}


@admin_router.put("/content/{kind}/{item_id}")
def admin_update_content(
    kind: str,
    item_id: str,
    body: ContentSeoIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.update_content_seo(db, kind, item_id, body.model_dump(exclude_unset=True))


@admin_router.post("/content/{kind}/{item_id}/toggle-index")
def admin_toggle_index(
    kind: str,
    item_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.toggle_index(db, kind, item_id)


@admin_router.post("/content/{kind}/{item_id}/request-indexing")
def admin_request_indexing(
    kind: str,
    item_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.request_indexing(db, kind, item_id)


@admin_router.get("/redirects")
def admin_list_redirects(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return {"items": svc.list_redirects(db)}


@admin_router.post("/redirects")
def admin_create_redirect(
    body: RedirectIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.create_redirect(db, body.model_dump())


@admin_router.delete("/redirects/{redirect_id}")
def admin_delete_redirect(
    redirect_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    svc.delete_redirect(db, redirect_id)
    return {"ok": True}


@admin_router.get("/sitemap")
def admin_sitemap_stats(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.sitemap_stats(db)


@admin_router.post("/sitemap/regenerate")
def admin_sitemap_regen(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.regenerate_sitemap(db)


@admin_router.post("/sitemap/submit-google")
def admin_sitemap_submit(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.submit_sitemap_to_google(db)


@admin_router.put("/robots")
def admin_save_robots(
    body: RobotsIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    row = svc.update_settings(db, {"robots_txt": body.robots_txt})
    return {"robots_txt": row.robots_txt}


@admin_router.post("/indexnow/generate-key")
def admin_indexnow_key(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.generate_indexnow_key(db)


@admin_router.post("/indexnow/notify")
def admin_indexnow_notify(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.notify_indexnow(db)


@admin_router.get("/health")
def admin_health(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.health_to_dict(svc.ensure_health(db))


@admin_router.post("/health/psi")
def admin_health_psi(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.run_psi_check(db)


@admin_router.post("/health/broken-links/scan")
def admin_broken_scan(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.scan_broken_links(db)


@admin_router.post("/health/broken-links/mark-fixed")
def admin_broken_fixed(
    body: MarkFixedIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.mark_broken_fixed(db, body.url)


@admin_router.get("/settings")
def admin_get_settings(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.settings_to_admin_with_oauth(db, svc.ensure_settings(db))


@admin_router.put("/settings")
def admin_put_settings(
    body: SettingsIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    row = svc.update_settings(db, body.model_dump(exclude_unset=True))
    return svc.settings_to_admin_with_oauth(db, row)


@admin_router.post("/settings/connect-psi")
def admin_connect_psi(
    body: PsiConnectIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.connect_psi(db, body.api_key)


@admin_router.post("/settings/connect-moz")
def admin_connect_moz(
    body: MozConnectIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    return svc.connect_moz(db, body.access_id, body.secret_key)


@admin_router.get("/gsc/oauth/start")
def admin_gsc_oauth_start(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    try:
        return {"authorize_url": gsc_oauth_start(db)}
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.get("/gsc/oauth/callback")
def admin_gsc_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    origin = admin_redirect_origin()
    target = f"{origin}/marketing/seo-control"
    if error:
        return RedirectResponse(url=f"{target}?gsc=error&message={quote(error[:200])}")
    try:
        gsc_oauth_complete(db, code=code, state=state)
    except ValueError as exc:
        return RedirectResponse(url=f"{target}?tab=settings&gsc=error&message={quote(str(exc)[:200])}")
    return RedirectResponse(url=f"{target}?tab=settings&gsc=connected")


@admin_router.post("/gsc/disconnect")
def admin_gsc_disconnect(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return disconnect_gsc(db)


@admin_router.post("/gsc/refresh")
def admin_gsc_refresh(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return refresh_gsc_metrics(db)


@admin_router.post("/upload-image")
async def admin_upload_image(
    file: UploadFile = File(...),
    _admin=Depends(require_platform_admin),
):
    url = await save_uploaded_theme_image(file)
    return {"image_url": url, "width": 1200, "height": 900, "format": "webp"}


# ---- Public ----


@public_router.get("/seo/settings")
def public_seo_settings(db: Session = Depends(get_db)):
    return svc.settings_to_public(svc.ensure_settings(db))


@public_router.get("/seo/robots.txt")
def public_robots(db: Session = Depends(get_db)):
    row = svc.ensure_settings(db)
    return {"robots_txt": row.robots_txt or svc.DEFAULT_ROBOTS}


@public_router.get("/seo/sitemap-entries")
def public_sitemap_entries(db: Session = Depends(get_db)):
    return {"entries": svc.build_sitemap_entries(db), **svc.sitemap_stats(db)}


@public_router.get("/seo/resolve-redirect")
def public_resolve_redirect(path: str, db: Session = Depends(get_db)):
    hit = svc.resolve_redirect(db, path)
    if not hit:
        return {"redirect": None}
    return {"redirect": hit}


@public_router.get("/seo/indexnow-key")
def public_indexnow_key(db: Session = Depends(get_db)):
    row = svc.ensure_settings(db)
    return {"key": row.indexnow_key or ""}


@public_router.get("/faq")
def public_faq_list(db: Session = Depends(get_db)):
    return {"items": svc.public_faq_list(db)}


@public_router.get("/faq/{slug}")
def public_faq_item(slug: str, db: Session = Depends(get_db)):
    return svc.public_faq_by_slug(db, slug)


@public_router.get("/seo/content/{kind}/{slug}")
def public_content_seo(kind: str, slug: str, db: Session = Depends(get_db)):
    return svc.public_content_seo(db, kind, slug)
