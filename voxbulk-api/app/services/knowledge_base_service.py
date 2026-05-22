from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.agent_knowledge_file import AgentKnowledgeFile
from app.models.knowledge_base_file import KnowledgeBaseFile

KB_SCOPE_LEAD = "lead"
KB_SCOPE_SALES = "sales"
KB_SCOPE_ORG = "org"
KB_SCOPES = frozenset({KB_SCOPE_LEAD, KB_SCOPE_SALES, KB_SCOPE_ORG})

# Recommended limits
MAX_KB_FILE_BYTES = 2 * 1024 * 1024  # 2 MB per .md file
MAX_KB_LIBRARY_FILES = 100
MAX_KB_FILES_PER_AGENT = 20
MAX_KB_FILES_PER_SCOPE = 20
# Cached on agent.kb_context for low-latency runtime (no disk read per turn)
MAX_KB_CONTEXT_CHARS = 20_000
MAX_KB_FILE_CHARS_FOR_CONTEXT = 8_000

_REPO_ROOT = Path(__file__).resolve().parents[2]
KB_ROOT = _REPO_ROOT / "data" / "knowledge-base"


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._")
    return cleaned or "document.md"


def ensure_kb_root() -> Path:
    KB_ROOT.mkdir(parents=True, exist_ok=True)
    return KB_ROOT


def normalize_kb_scope(scope: str | None, *, default: str = KB_SCOPE_ORG) -> str:
    s = (scope or default).strip().lower()
    if s not in KB_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid knowledge base scope. Use one of: {', '.join(sorted(KB_SCOPES))}.",
        )
    return s


def kb_file_out(row: KnowledgeBaseFile) -> dict:
    return {
        "id": row.id,
        "original_filename": row.original_filename,
        "storage_path": row.storage_path,
        "size_bytes": row.size_bytes,
        "scope": str(row.scope or KB_SCOPE_ORG),
        "created_at": row.created_at,
        "uploaded_by_user_id": row.uploaded_by_user_id,
    }


def list_kb_files(db: Session, *, scope: str | None = None) -> list[dict]:
    stmt = select(KnowledgeBaseFile).order_by(KnowledgeBaseFile.created_at.desc())
    if scope is not None:
        stmt = stmt.where(KnowledgeBaseFile.scope == normalize_kb_scope(scope))
    rows = list(db.execute(stmt).scalars())
    return [kb_file_out(r) for r in rows]


def get_kb_file(db: Session, file_id: str) -> dict:
    row = db.execute(select(KnowledgeBaseFile).where(KnowledgeBaseFile.id == file_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base file not found")
    content = read_kb_file_text(row)
    return {**kb_file_out(row), "content": content, "content_chars": len(content)}


async def upload_kb_file(
    db: Session,
    *,
    file: UploadFile,
    uploaded_by_user_id: str | None,
    scope: str = KB_SCOPE_ORG,
) -> dict:
    ensure_kb_root()
    kb_scope = normalize_kb_scope(scope)
    total = db.execute(select(func.count()).select_from(KnowledgeBaseFile)).scalar_one()
    if int(total) >= MAX_KB_LIBRARY_FILES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Knowledge base library limit reached ({MAX_KB_LIBRARY_FILES} files)")

    scoped_count = db.execute(
        select(func.count()).select_from(KnowledgeBaseFile).where(KnowledgeBaseFile.scope == kb_scope)
    ).scalar_one()
    if int(scoped_count) >= MAX_KB_FILES_PER_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Knowledge base limit reached for scope '{kb_scope}' ({MAX_KB_FILES_PER_SCOPE} files). Delete unused files first.",
        )

    original = _safe_filename(file.filename or "document.md")
    if not original.lower().endswith(".md"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .md files are allowed")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    if len(raw) > MAX_KB_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large (max {MAX_KB_FILE_BYTES // (1024 * 1024)} MB)",
        )

    row = KnowledgeBaseFile(
        original_filename=original,
        storage_path="",
        size_bytes=len(raw),
        scope=kb_scope,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    db.add(row)
    db.flush()

    rel_path = f"data/knowledge-base/{row.id}_{original}"
    abs_path = _REPO_ROOT / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(raw)

    row.storage_path = rel_path.replace("\\", "/")
    db.add(row)
    db.commit()
    db.refresh(row)
    return kb_file_out(row)


def _prune_kb_file_from_agent_settings(db: Session, file_id: str) -> None:
    """Drop deleted file IDs from Jode/Adam settings and refresh cached KB context."""
    from app.models.frontpage_call_setting import FrontpageCallSetting
    from app.models.lead_sales_setting import LeadSalesSetting
    from app.services.frontpage_lead_service import dump_kb_file_ids, parse_kb_file_ids

    clean_id = str(file_id or "").strip()
    if not clean_id:
        return

    frontpage = db.get(FrontpageCallSetting, "default")
    if frontpage is not None:
        ids = [fid for fid in parse_kb_file_ids(frontpage.kb_file_ids) if fid != clean_id]
        if ids != parse_kb_file_ids(frontpage.kb_file_ids):
            ids = sanitize_kb_file_ids(db, ids, scope=KB_SCOPE_LEAD)
            frontpage.kb_file_ids = dump_kb_file_ids(ids)
            files = get_kb_files_by_ids(db, ids, scope=KB_SCOPE_LEAD)
            frontpage.kb_context = build_kb_context_text(files) or None
            db.add(frontpage)

    sales = db.get(LeadSalesSetting, "default")
    if sales is not None:
        ids = [fid for fid in parse_kb_file_ids(sales.kb_file_ids) if fid != clean_id]
        if ids != parse_kb_file_ids(sales.kb_file_ids):
            ids = sanitize_kb_file_ids(db, ids, scope=KB_SCOPE_SALES)
            sales.kb_file_ids = dump_kb_file_ids(ids)
            files = get_kb_files_by_ids(db, ids, scope=KB_SCOPE_SALES)
            sales.kb_context = build_kb_context_text(files) or None
            db.add(sales)


def delete_kb_file(db: Session, *, file_id: str) -> None:
    row = db.execute(select(KnowledgeBaseFile).where(KnowledgeBaseFile.id == file_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base file not found")

    abs_path = _REPO_ROOT / row.storage_path
    if abs_path.is_file():
        try:
            abs_path.unlink()
        except OSError:
            pass

    db.execute(delete(AgentKnowledgeFile).where(AgentKnowledgeFile.knowledge_base_file_id == file_id))
    _prune_kb_file_from_agent_settings(db, file_id)
    db.delete(row)
    db.commit()


def get_kb_files_by_ids(db: Session, file_ids: list[str], *, scope: str | None = None) -> list[KnowledgeBaseFile]:
    if not file_ids:
        return []
    rows = list(db.execute(select(KnowledgeBaseFile).where(KnowledgeBaseFile.id.in_(file_ids))).scalars())
    by_id = {r.id: r for r in rows}
    if scope is not None:
        expected = normalize_kb_scope(scope)
        rows = [by_id[fid] for fid in file_ids if fid in by_id and str(by_id[fid].scope or KB_SCOPE_ORG) == expected]
    else:
        rows = [by_id[fid] for fid in file_ids if fid in by_id]
    return rows


def sanitize_kb_file_ids(db: Session, file_ids: list[str], *, scope: str | None = None) -> list[str]:
    """Keep only IDs that still exist in the library (optionally scoped). Drops stale links."""
    unique = list(dict.fromkeys([str(v).strip() for v in file_ids if str(v).strip()]))
    if not unique:
        return []
    rows = list(db.execute(select(KnowledgeBaseFile).where(KnowledgeBaseFile.id.in_(unique))).scalars())
    by_id = {r.id: r for r in rows}
    out: list[str] = []
    for fid in unique:
        row = by_id.get(fid)
        if row is None:
            continue
        if scope is not None and str(row.scope or KB_SCOPE_ORG) != normalize_kb_scope(scope):
            continue
        out.append(fid)
    return out


def validate_kb_file_ids_for_scope(db: Session, file_ids: list[str], *, scope: str) -> list[str]:
    """Return file IDs that exist and match scope. Stale/missing IDs are dropped (no error)."""
    return sanitize_kb_file_ids(db, file_ids, scope=scope)


def prune_orphan_agent_knowledge_links(db: Session, *, agent_id: str | None = None) -> list[str]:
    """Drop agent→KB links when the KB row no longer exists (e.g. after DB restore)."""
    stmt = select(AgentKnowledgeFile)
    if agent_id:
        stmt = stmt.where(AgentKnowledgeFile.agent_id == agent_id)
    links = list(db.execute(stmt).scalars())
    if not links:
        return []
    valid_ids = set(db.execute(select(KnowledgeBaseFile.id)).scalars())
    pruned: list[str] = []
    for link in links:
        if link.knowledge_base_file_id not in valid_ids:
            pruned.append(link.knowledge_base_file_id)
            db.delete(link)
    if pruned:
        db.commit()
    return pruned


def agent_knowledge_file_ids(db: Session, agent_id: str, *, prune_orphans: bool = True) -> list[str]:
    if prune_orphans:
        prune_orphan_agent_knowledge_links(db, agent_id=agent_id)
    return list(
        db.execute(
            select(AgentKnowledgeFile.knowledge_base_file_id).where(AgentKnowledgeFile.agent_id == agent_id)
        ).scalars()
    )


def read_kb_file_text(row: KnowledgeBaseFile) -> str:
    abs_path = _REPO_ROOT / str(row.storage_path or "")
    if not abs_path.is_file():
        return ""
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > MAX_KB_FILE_CHARS_FOR_CONTEXT:
        text = text[:MAX_KB_FILE_CHARS_FOR_CONTEXT] + "\n\n[... truncated for context limit ...]"
    return text


def compose_prompt_from_kb_files(files: list[KnowledgeBaseFile]) -> str:
    """Use selected .md files verbatim as the system prompt (no AI rewrite)."""
    if not files:
        return ""
    blocks: list[str] = []
    for row in files:
        body = read_kb_file_text(row)
        if not body:
            continue
        blocks.append(f"# {row.original_filename}\n\n{body}")
    return "\n\n---\n\n".join(blocks).strip()


def build_kb_context_text(files: list[KnowledgeBaseFile]) -> str:
    if not files:
        return ""
    blocks: list[str] = []
    total = 0
    for row in files:
        body = read_kb_file_text(row)
        if not body:
            continue
        header = f"### {row.original_filename} ({row.storage_path})"
        block = f"{header}\n{body}"
        if total + len(block) > MAX_KB_CONTEXT_CHARS:
            remaining = MAX_KB_CONTEXT_CHARS - total
            if remaining > 200:
                blocks.append(block[:remaining] + "\n\n[... knowledge base context truncated ...]")
            break
        blocks.append(block)
        total += len(block) + 2
    return "\n\n---\n\n".join(blocks)


def refresh_agent_kb_context(db: Session, agent_id: str) -> str | None:
    from app.models.agent import AgentDefinition

    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        return None
    file_ids = agent_knowledge_file_ids(db, agent_id)
    files = get_kb_files_by_ids(db, file_ids)
    context = build_kb_context_text(files) or None
    agent.kb_context = context
    db.add(agent)
    db.commit()
    return context


def set_agent_knowledge_files(db: Session, *, agent_id: str, file_ids: list[str]) -> list[str]:
    unique = list(dict.fromkeys([str(v).strip() for v in file_ids if str(v).strip()]))
    if len(unique) > MAX_KB_FILES_PER_AGENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {MAX_KB_FILES_PER_AGENT} knowledge base files per agent",
        )
    if unique:
        existing_rows = list(db.execute(select(KnowledgeBaseFile).where(KnowledgeBaseFile.id.in_(unique))).scalars())
        existing = {r.id for r in existing_rows}
        unique = [fid for fid in unique if fid in existing]
        non_org = [r.original_filename for r in existing_rows if str(r.scope or KB_SCOPE_ORG) != KB_SCOPE_ORG]
        if non_org:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Lead/sales knowledge base files cannot attach to clinic agents: {', '.join(non_org)}",
            )

    db.execute(delete(AgentKnowledgeFile).where(AgentKnowledgeFile.agent_id == agent_id))
    for fid in unique:
        db.add(AgentKnowledgeFile(agent_id=agent_id, knowledge_base_file_id=fid))
    db.commit()
    refresh_agent_kb_context(db, agent_id)
    return unique
