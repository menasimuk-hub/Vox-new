"""Review manifest generation and approval for marketing → utility purge batches."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_telnyx_push_service import (
    collect_used_cfs_meta_names,
    suggest_next_cfs_version_name,
)
from app.services.survey_wa_utility_rewrite_service import (
    DEFAULT_UTILITY_LLM_MODEL,
    DEFAULT_UTILITY_LLM_PROVIDER,
    _extract_body_and_buttons,
    _find_template_row,
    discover_remote_marketing_templates,
    lang_variant_from_manifest_item,
    parse_cfs_meta_name,
    resolve_utility_llm_config,
)
from app.services.survey_whatsapp_template_service import _effective_components
from app.services.wa_marketing_utility_multilang_service import (
    build_groups_from_candidates,
    rewrite_group_variants,
)
from app.services.wa_template_meta_sync import suggest_utility_clone_template_name
from app.services.wa_template_utility_lint import lint_utility_template
from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

REVIEW_ROOT = Path(__file__).resolve().parents[2] / "seed-data" / "wa-survey" / "migration-reports" / "marketing-utility-review"


def review_batch_dir(batch_id: str) -> Path:
    clean = re.sub(r"[^\w\-]", "", str(batch_id or "").strip())
    if not clean:
        raise ValueError("batch_id is required")
    return REVIEW_ROOT / clean


def manifest_path(batch_id: str) -> Path:
    return review_batch_dir(batch_id) / "manifest.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _survey_rename_preview(db: Session, row: TelnyxWhatsappTemplate, remote_name: str) -> str:
    from app.services.survey_whatsapp_template_service import _has_remote_telnyx_id

    if str(row.status or "").upper() not in {"APPROVED", "PENDING"} or not _has_remote_telnyx_id(row):
        return str(row.name or remote_name)
    used = {
        str(r[0]).strip().lower()
        for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
        if r[0]
    }
    if is_was_survey_name(row.name):
        return suggest_next_was_seq_name(row.name, used_names=used) or str(row.name or remote_name)
    return suggest_utility_clone_template_name(row.name) or f"{row.name}_utu"


def _feedback_rename_preview(db: Session, row: FeedbackWaTemplate, remote_name: str) -> str:
    current = str(getattr(row, "meta_template_name", "") or remote_name).strip().lower()
    used = collect_used_cfs_meta_names(db)
    bumped = suggest_next_cfs_version_name(current, used_names=used)
    return bumped or current


def _enrich_candidates(db: Session, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in candidates:
        if not item.get("actionable"):
            enriched.append(dict(item))
            continue
        copy = dict(item)
        product = str(copy.get("product") or "survey")
        if product == "survey":
            row = None
            if copy.get("id"):
                row = db.get(TelnyxWhatsappTemplate, int(copy["id"]))
            if row is None:
                row = _find_template_row(db, str(copy.get("process_name") or copy.get("name") or ""))
            if row is not None:
                components = _effective_components(row)
                body, buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])
                copy["full_body"] = body
                copy["buttons"] = buttons
                copy["body_preview"] = body[:160]
        elif product == "feedback":
            fid = copy.get("feedback_template_id") or copy.get("id")
            row = db.get(FeedbackWaTemplate, str(fid)) if fid else None
            if row is not None:
                body = str(row.body_text or "").strip()
                buttons: list[str] = []
                if row.buttons_json:
                    try:
                        parsed = json.loads(row.buttons_json)
                        if isinstance(parsed, list):
                            buttons = [str(x).strip() for x in parsed if str(x).strip()]
                    except json.JSONDecodeError:
                        pass
                copy["full_body"] = body
                copy["buttons"] = buttons
                copy["body_preview"] = body[:160]
        enriched.append(copy)
    return enriched


def _recount_statuses(manifest: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            status = str(item.get("status") or "listed")
            counts[status] = counts.get(status, 0) + 1
    manifest["status_counts"] = counts
    return counts


def _profile_labels(overview: dict[str, Any]) -> tuple[str, str]:
    meta_label = telnyx_label = "—"
    for profile in overview.get("profiles") or []:
        if not profile.get("ok"):
            continue
        label = str(profile.get("profile_label") or profile.get("provider") or "")
        provider = str(profile.get("provider") or "").lower()
        if provider == "meta":
            meta_label = label
        elif provider == "telnyx":
            telnyx_label = label
    return meta_label, telnyx_label


def create_marketing_list_manifest(
    db: Session,
    *,
    batch_id: str,
    name_contains: str | None = None,
    limit: int = 0,
) -> dict[str, Any]:
    """Step 1: pull MARKETING from Meta + Telnyx, save manifest (status=listed). No LLM."""
    overview, candidates = discover_remote_marketing_templates(db, name_contains=name_contains)
    enriched = _enrich_candidates(db, candidates)
    actionable = [c for c in enriched if c.get("actionable")]
    if limit and limit > 0:
        actionable = actionable[:limit]

    groups_map: dict[str, dict[str, Any]] = {}
    for item in actionable:
        product = str(item.get("product") or "survey")
        remote_name = str(item.get("remote_name") or item.get("name") or "")
        from app.services.wa_marketing_utility_multilang_service import parse_group_key

        group_key = parse_group_key(remote_name, product=product)
        group = groups_map.setdefault(
            group_key,
            {"group_key": group_key, "product": product, "status": "listed", "items": []},
        )
        body = str(item.get("full_body") or item.get("body_preview") or "")
        action = "feedback_rewrite_push" if product == "feedback" else "survey_rewrite_push"
        cfs = parse_cfs_meta_name(remote_name) if product == "feedback" else None
        lang = item.get("remote_language") or item.get("language")
        if cfs and cfs.get("lang") and (not lang or str(lang).lower().startswith("en")):
            lang = f"{cfs['lang']}_gb"
        group["items"].append(
            {
                "status": "listed",
                "action": action,
                "product": product,
                "local_template_id": item.get("id") or item.get("feedback_template_id"),
                "label": str(item.get("name") or remote_name),
                "remote_name": remote_name,
                "new_meta_name": None,
                "language": lang,
                "body_before": body,
                "body_after": None,
                "rewritten": False,
                "remote_status": item.get("status"),
                "remote_profiles": item.get("remote_profiles"),
                "buttons": item.get("buttons") or [],
                "industry_slug": item.get("industry_slug") or (cfs.get("industry") if cfs else None),
                "template_key": item.get("template_key") or (cfs.get("topic_key") if cfs else None),
                "topic_name": item.get("survey_type") or item.get("template_key") or (cfs.get("topic") if cfs else None),
                "meta": {"reasons": item.get("reasons")},
            }
        )

    llm_cfg = resolve_utility_llm_config(db)
    meta_label, telnyx_label = _profile_labels(overview)
    manifest_groups = list(groups_map.values())
    batch_dir = review_batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "created_at": _now_iso(),
        "workflow_step": "listed",
        "llm_provider": llm_cfg["provider"],
        "llm_model": llm_cfg["model"],
        "deepinfra_base_url": llm_cfg["base_url"],
        "profiles": {"meta": meta_label, "telnyx": telnyx_label},
        "overview": overview,
        "groups": manifest_groups,
    }
    _recount_statuses(manifest)
    save_manifest(batch_id, manifest)
    _write_overview_md(batch_dir, manifest)
    return manifest


def run_batch_rewrites(
    db: Session,
    *,
    batch_id: str,
    use_llm: bool = True,
    limit_groups: int = 0,
) -> dict[str, Any]:
    """Step 3: Qwen rewrite for items with status=approved_rewrite."""
    from app.services.survey_wa_utility_rewrite_service import resolve_utility_llm_config
    from app.services.wa_marketing_utility_multilang_service import (
        TemplateGroup,
        rewrite_group_variants,
    )

    manifest = load_manifest(batch_id)
    llm_cfg = resolve_utility_llm_config(db)
    llm_provider = llm_cfg["provider"]
    llm_model = llm_cfg["model"]
    rewritten = 0
    groups_to_run: list[TemplateGroup] = []
    group_index: dict[str, dict[str, Any]] = {}

    for group in manifest.get("groups") or []:
        variants: list[LangVariant] = []
        for item in group.get("items") or []:
            if str(item.get("status") or "") != "approved_rewrite":
                continue
            variants.append(lang_variant_from_manifest_item(item))
        if variants:
            groups_to_run.append(TemplateGroup(group_key=str(group.get("group_key")), product=str(group.get("product")), variants=variants))
            group_index[str(group.get("group_key"))] = group

    if limit_groups and limit_groups > 0:
        groups_to_run = groups_to_run[:limit_groups]

    for tg in groups_to_run:
        rewrite_group_variants(
            db,
            tg,
            use_llm=use_llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        group = group_index[tg.group_key]
        variant_by_id = {str(v.local_template_id): v for v in tg.variants}
        for item in group.get("items") or []:
            variant = variant_by_id.get(str(item.get("local_template_id")))
            if variant is None:
                continue
            body_after = variant.body_after or variant.body_before
            lint = lint_utility_template(
                body=body_after,
                buttons=variant.buttons,
                language=variant.language,
                meta_category="utility",
                template_key=variant.template_key,
            )
            new_name = str(item.get("remote_name") or "")
            if variant.product == "survey" and variant.local_template_id:
                row = db.get(TelnyxWhatsappTemplate, int(variant.local_template_id))
                if row is not None:
                    new_name = _survey_rename_preview(db, row, variant.remote_name)
            elif variant.product == "feedback" and variant.local_template_id:
                row = db.get(FeedbackWaTemplate, str(variant.local_template_id))
                if row is not None:
                    new_name = _feedback_rename_preview(db, row, variant.remote_name)
            will_delete = bool(variant.remote_name and new_name.lower() != variant.remote_name.lower())
            item.update(
                {
                    "status": "rewritten",
                    "body_after": body_after,
                    "rewritten": variant.rewritten,
                    "skip_reason": variant.skip_reason,
                    "new_meta_name": new_name,
                    "delete_old_remote_name": variant.remote_name if will_delete else None,
                    "lint_ok": lint.ok,
                    "lint_messages": [i.message for i in lint.issues[:5]],
                }
            )
            group["anchor_lang"] = tg.anchor_lang
            group["aligned_langs"] = tg.aligned_langs
            group["inconsistent_langs"] = tg.inconsistent_langs
            group["audit_notes"] = tg.audit_notes
            rewritten += 1
        _write_group_review(review_batch_dir(batch_id), group)

    manifest["workflow_step"] = "rewritten"
    manifest["rewritten_at"] = _now_iso()
    manifest["llm_provider"] = llm_provider
    manifest["llm_model"] = llm_model
    _recount_statuses(manifest)
    save_manifest(batch_id, manifest)
    _write_overview_md(review_batch_dir(batch_id), manifest)
    return {"rewritten": rewritten, "status_counts": manifest["status_counts"], "llm_model": llm_model}


def print_listed_templates(manifest: dict[str, Any]) -> None:
    overview = manifest.get("overview") or {}
    meta_label, telnyx_label = _profile_labels(overview)
    print("=" * 72)
    print("STEP 1 — MARKETING templates on Meta + Telnyx (no changes yet)")
    print("=" * 72)
    print(f"Batch ID:     {manifest.get('batch_id')}")
    print(f"Meta profile: {meta_label}")
    print(f"Telnyx profile: {telnyx_label}")
    print(
        f"MARKETING count — Meta: {overview.get('remote_marketing_meta', '—')} | "
        f"Telnyx: {overview.get('remote_marketing_telnyx', '—')}"
    )
    print(f"Listed items: {(manifest.get('status_counts') or {}).get('listed', 0)}")
    print("")
    n = 0
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            n += 1
            print(f"--- [{n}] {item.get('remote_name')} ({item.get('language')}) ---")
            print(f"    product: {item.get('product')} | local id: {item.get('local_template_id')}")
            print(f"    status:  {item.get('status')}")
            print(f"    BODY:")
            for line in str(item.get("body_before") or "").splitlines():
                print(f"      {line}")
            print("")
    print("NEXT — approve which templates to rewrite:")
    print(f"  python scripts/purge_marketing_wa_templates.py approve-rewrite --batch-id {manifest.get('batch_id')} --all")
    print(f"  python scripts/purge_marketing_wa_templates.py approve-rewrite --batch-id {manifest.get('batch_id')} --names was_restaurant_*")


def print_rewritten_templates(manifest: dict[str, Any]) -> None:
    print("=" * 72)
    print("STEP 3 — REWRITE results (before → after)")
    print("=" * 72)
    print(f"Batch ID: {manifest.get('batch_id')}")
    print(f"LLM: {manifest.get('llm_provider')} / {manifest.get('llm_model')} (DeepInfra from Admin DB)")
    print("")
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            if str(item.get("status") or "") not in {"rewritten", "approved_push", "pushed"}:
                continue
            print(f"--- {item.get('remote_name')} → {item.get('new_meta_name')} ---")
            print(f"    status: {item.get('status')} | rewritten: {item.get('rewritten')} | lint_ok: {item.get('lint_ok')}")
            if item.get("skip_reason"):
                print(f"    skip_reason: {item.get('skip_reason')}")
            print("    BEFORE:")
            for line in str(item.get("body_before") or "").splitlines():
                print(f"      {line}")
            print("    AFTER:")
            for line in str(item.get("body_after") or "").splitlines():
                print(f"      {line}")
            print("")
    print("NEXT — approve push to Meta + Telnyx:")
    print(f"  python scripts/purge_marketing_wa_templates.py approve-push --batch-id {manifest.get('batch_id')} --all")


def generate_review_batch(
    db: Session,
    *,
    batch_id: str,
    use_llm: bool = True,
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = DEFAULT_UTILITY_LLM_MODEL,
    limit_groups: int = 0,
    name_contains: str | None = None,
) -> dict[str, Any]:
    overview, candidates = discover_remote_marketing_templates(db, name_contains=name_contains)
    enriched = _enrich_candidates(db, candidates)
    groups = build_groups_from_candidates(enriched)
    if limit_groups and limit_groups > 0:
        groups = groups[:limit_groups]

    manifest_groups: list[dict[str, Any]] = []
    for group in groups:
        rewrite_group_variants(
            db,
            group,
            use_llm=use_llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        group_items: list[dict[str, Any]] = []
        for variant in group.variants:
            new_name = variant.remote_name
            lint_ok = True
            lint_msgs: list[str] = []
            body_after = variant.body_after or variant.body_before
            lint = lint_utility_template(
                body=body_after,
                buttons=variant.buttons,
                language=variant.language,
                meta_category="utility",
                template_key=variant.template_key,
            )
            lint_ok = lint.ok
            lint_msgs = [i.message for i in lint.issues[:5]]

            action = "feedback_rewrite_push" if variant.product == "feedback" else "survey_rewrite_push"
            if variant.product == "survey" and variant.local_template_id:
                row = db.get(TelnyxWhatsappTemplate, int(variant.local_template_id))
                if row is not None:
                    new_name = _survey_rename_preview(db, row, variant.remote_name)
            elif variant.product == "feedback" and variant.local_template_id:
                row = db.get(FeedbackWaTemplate, str(variant.local_template_id))
                if row is not None:
                    new_name = _feedback_rename_preview(db, row, variant.remote_name)

            variant.new_meta_name = new_name
            will_delete = bool(variant.remote_name and new_name.lower() != variant.remote_name.lower())
            group_items.append(
                {
                    "status": "pending",
                    "action": action,
                    "product": variant.product,
                    "local_template_id": variant.local_template_id,
                    "label": variant.label,
                    "remote_name": variant.remote_name,
                    "new_meta_name": new_name,
                    "language": variant.language,
                    "body_before": variant.body_before,
                    "body_after": body_after,
                    "rewritten": variant.rewritten,
                    "skip_reason": variant.skip_reason,
                    "delete_old_remote_name": variant.remote_name if will_delete else None,
                    "lint_ok": lint_ok,
                    "lint_messages": lint_msgs,
                    "buttons": variant.buttons,
                    "meta": variant.meta,
                }
            )
        manifest_groups.append(
            {
                "group_key": group.group_key,
                "product": group.product,
                "status": "pending",
                "anchor_lang": group.anchor_lang,
                "aligned_langs": group.aligned_langs,
                "inconsistent_langs": group.inconsistent_langs,
                "audit_notes": group.audit_notes,
                "items": group_items,
            }
        )

    batch_dir = review_batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "created_at": _now_iso(),
        "llm_provider": llm_provider,
        "llm_model": llm_model or DEFAULT_UTILITY_LLM_MODEL,
        "overview": overview,
        "status_counts": {
            "pending": sum(len(g["items"]) for g in manifest_groups),
            "approved": 0,
            "pushed": 0,
            "failed": 0,
        },
        "groups": manifest_groups,
    }
    manifest_path(batch_id).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_overview_md(batch_dir, manifest)
    for group_entry in manifest_groups:
        _write_group_review(batch_dir, group_entry)
    return manifest


def _write_overview_md(batch_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"# Marketing → Utility review — {manifest.get('batch_id')}",
        "",
        f"Created: {manifest.get('created_at')}",
        f"LLM: {manifest.get('llm_provider')} / {manifest.get('llm_model')}",
        "",
        "## Summary",
        "",
    ]
    overview = manifest.get("overview") or {}
    lines.append(f"- Meta MARKETING count: {overview.get('remote_marketing_meta', '—')}")
    lines.append(f"- Telnyx MARKETING count: {overview.get('remote_marketing_telnyx', '—')}")
    lines.append(f"- Unique remote MARKETING: {overview.get('unique_remote_marketing', '—')}")
    lines.append(f"- Actionable local matches: {overview.get('actionable_local_matches', '—')}")
    by_product = overview.get("by_product") or {}
    lines.append(f"- By product: survey={by_product.get('survey', 0)}, feedback={by_product.get('feedback', 0)}")
    lines.append("")
    lines.append("| Group | Product | Langs | Status |")
    lines.append("|-------|---------|-------|--------|")
    for group in manifest.get("groups") or []:
        langs = ", ".join(str(i.get("language") or "") for i in group.get("items") or [])
        lines.append(
            f"| {group.get('group_key')} | {group.get('product')} | {langs} | {group.get('status')} |"
        )
    (batch_dir / "overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_group_review(batch_dir: Path, group: dict[str, Any]) -> None:
    key = re.sub(r"[^\w\-]", "_", str(group.get("group_key") or "group"))
    group_dir = batch_dir / "groups" / key
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "review.json").write_text(json.dumps(group, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# {group.get('group_key')}",
        "",
        f"Product: **{group.get('product')}**",
        f"Anchor: {group.get('anchor_lang')}",
        f"Aligned: {', '.join(group.get('aligned_langs') or []) or '—'}",
        f"Inconsistent: {', '.join(group.get('inconsistent_langs') or []) or '—'}",
        f"Audit: {group.get('audit_notes') or '—'}",
        "",
    ]
    for item in group.get("items") or []:
        lines.extend(
            [
                f"## {item.get('label')} ({item.get('language')})",
                "",
                f"- Status: {item.get('status')}",
                f"- Remote: `{item.get('remote_name')}` → `{item.get('new_meta_name')}`",
                f"- Rewritten: {item.get('rewritten')} ({item.get('skip_reason') or 'n/a'})",
                f"- Lint OK: {item.get('lint_ok')}",
                "",
                "### Before",
                "",
                str(item.get("body_before") or ""),
                "",
                "### After",
                "",
                str(item.get("body_after") or ""),
                "",
            ]
        )
    (group_dir / "review.md").write_text("\n".join(lines), encoding="utf-8")


def load_manifest(batch_id: str) -> dict[str, Any]:
    path = manifest_path(batch_id)
    if not path.is_file():
        raise FileNotFoundError(f"Review batch not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(batch_id: str, manifest: dict[str, Any]) -> None:
    manifest_path(batch_id).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _matches_filter(item: dict[str, Any], *, names: list[str] | None, ids: list[str] | None) -> bool:
    if not names and not ids:
        return True
    label = str(item.get("label") or "").strip().lower()
    remote = str(item.get("remote_name") or "").strip().lower()
    local_id = str(item.get("local_template_id") or "")
    if ids and local_id in {str(x).strip() for x in ids}:
        return True
    if names:
        for pattern in names:
            pat = str(pattern or "").strip().lower()
            if not pat:
                continue
            if pat in label or pat in remote or label == pat or remote == pat:
                return True
            if pat.endswith("*") and (label.startswith(pat[:-1]) or remote.startswith(pat[:-1])):
                return True
    return False


def reset_rewritten_items(
    batch_id: str,
    *,
    names: list[str] | None = None,
    reset_all: bool = False,
) -> dict[str, Any]:
    """Move rewritten items back to approved_rewrite so Step 3 can be re-run after a code fix."""
    manifest = load_manifest(batch_id)
    needles = [str(n or "").strip().lower() for n in (names or []) if str(n or "").strip()]
    reset = 0
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            if str(item.get("status") or "") != "rewritten":
                continue
            remote = str(item.get("remote_name") or item.get("label") or "").lower()
            if not reset_all and needles and not any(
                remote == needle or remote.startswith(needle.rstrip("*")) or needle.rstrip("*") in remote
                for needle in needles
            ):
                continue
            item["status"] = "approved_rewrite"
            item["body_after"] = None
            item["rewritten"] = False
            item["skip_reason"] = None
            item["lint_ok"] = None
            item["lint_messages"] = []
            reset += 1
    manifest["workflow_step"] = "approved_rewrite"
    counts = _recount_statuses(manifest)
    save_manifest(batch_id, manifest)
    return {"reset": reset, "status_counts": counts}


def approve_manifest_items(
    batch_id: str,
    *,
    names: list[str] | None = None,
    ids: list[str] | None = None,
    approve_all: bool = False,
    from_status: str = "listed",
    to_status: str = "approved_rewrite",
) -> dict[str, Any]:
    manifest = load_manifest(batch_id)
    approved = 0
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            current = str(item.get("status") or "")
            if current in {"pushed", "failed"}:
                continue
            if current != from_status:
                continue
            if approve_all or _matches_filter(item, names=names, ids=ids):
                item["status"] = to_status
                approved += 1
    manifest[f"{to_status}_at"] = _now_iso()
    counts = _recount_statuses(manifest)
    save_manifest(batch_id, manifest)
    _write_overview_md(review_batch_dir(batch_id), manifest)
    return {"approved": approved, "to_status": to_status, "status_counts": counts}


def update_manifest_item_status(
    batch_id: str,
    *,
    local_template_id: Any,
    label: str,
    status: str,
    error: str | None = None,
) -> None:
    manifest = load_manifest(batch_id)
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            if str(item.get("local_template_id")) == str(local_template_id) and str(item.get("label")) == str(label):
                item["status"] = status
                if error:
                    item["error"] = error
    _recount_statuses(manifest)
    save_manifest(batch_id, manifest)
