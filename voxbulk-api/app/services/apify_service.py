from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

APIFY_API_BASE = "https://api.apify.com/v2"


class ApifyServiceError(ValueError):
    pass


class ApifyService:
    @staticmethod
    def normalize_token(token: str | None) -> str:
        """Clean pasted Apify tokens so auth does not 401 on trivial paste issues."""
        key = str(token or "")
        # Strip BOM / zero-width / weird whitespace from copy-paste
        key = key.replace("\ufeff", "").replace("\u200b", "").replace("\u00a0", " ")
        key = key.strip().strip('"').strip("'")
        # People often paste "Bearer apify_api_…" or the full curl snippet
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        # Accidental query-string paste: …?token=apify_api_…
        m = re.search(r"(?:[?&]token=)([A-Za-z0-9_\-]+)", key)
        if m:
            key = m.group(1)
        # If a whole URL was pasted, pull token= value
        if "api.apify.com" in key and "token=" in key:
            m2 = re.search(r"token=([A-Za-z0-9_\-]+)", key)
            if m2:
                key = m2.group(1)
        key = "".join(ch for ch in key if ch.isprintable() and not ch.isspace())
        return key

    @staticmethod
    def token_fingerprint(token: str | None) -> str:
        key = ApifyService.normalize_token(token)
        if not key:
            return ""
        if len(key) <= 8:
            return key[:2] + "..."
        return f"{key[:6]}...{key[-4:]} (len={len(key)})"

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        key = ApifyService.normalize_token(token)
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    @staticmethod
    def _actor_path(actor_id: str) -> str:
        raw = str(actor_id or "").strip()
        if not raw:
            raise ApifyServiceError("Apify actor ID is required")
        # Accept username/actor-name or already-encoded id
        return quote(raw, safe="")

    @staticmethod
    def test_connection(token: str, *, actor_id: str | None = None) -> dict[str, Any]:
        key = ApifyService.normalize_token(token)
        if not key:
            raise ApifyServiceError("Apify API token is required — paste the token from Apify Console → Settings → Integrations")
        if len(key) < 20:
            raise ApifyServiceError(
                f"Apify token looks too short ({len(key)} chars). "
                "Copy the full token from Apify Console → Settings → Integrations (usually starts with apify_api_)."
            )
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{APIFY_API_BASE}/users/me", headers=ApifyService._headers(key))
                # Fallback: some environments reject header auth — try query token
                if resp.status_code == 401:
                    resp = client.get(
                        f"{APIFY_API_BASE}/users/me",
                        params={"token": key},
                        headers={"Content-Type": "application/json"},
                    )
                if resp.status_code == 401:
                    raise ApifyServiceError(
                        "Invalid Apify API token (Apify returned 401). "
                        "Copy a fresh token from https://console.apify.com/settings/integrations "
                        f"(received {ApifyService.token_fingerprint(key)})."
                    )
                if resp.status_code >= 400:
                    raise ApifyServiceError(f"Apify API error ({resp.status_code}): {resp.text[:300]}")
                user = (resp.json() or {}).get("data") or {}
                out: dict[str, Any] = {
                    "ok": True,
                    "message": "Apify connected",
                    "username": user.get("username") or user.get("email") or "",
                    "user_id": user.get("id"),
                    "token_fingerprint": ApifyService.token_fingerprint(key),
                }
                aid = str(actor_id or "").strip()
                if aid:
                    path = ApifyService._actor_path(aid)
                    actor_resp = client.get(f"{APIFY_API_BASE}/acts/{path}", headers=ApifyService._headers(key))
                    if actor_resp.status_code == 404:
                        raise ApifyServiceError(f"Actor not found: {aid}")
                    if actor_resp.status_code >= 400:
                        raise ApifyServiceError(
                            f"Actor check failed ({actor_resp.status_code}): {actor_resp.text[:300]}"
                        )
                    actor = (actor_resp.json() or {}).get("data") or {}
                    out["actor_id"] = aid
                    out["actor_name"] = actor.get("name") or actor.get("title") or aid
                    out["message"] = f"Apify connected · actor {out['actor_name']}"
                return out
        except ApifyServiceError:
            raise
        except Exception as exc:
            raise ApifyServiceError(str(exc)) from exc

    @staticmethod
    def start_actor_run(token: str, *, actor_id: str, run_input: dict[str, Any]) -> dict[str, Any]:
        key = ApifyService.normalize_token(token)
        if not key:
            raise ApifyServiceError("Apify API token is required")
        path = ApifyService._actor_path(actor_id)
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{APIFY_API_BASE}/acts/{path}/runs",
                    headers=ApifyService._headers(key),
                    json=run_input or {},
                )
                if resp.status_code >= 400:
                    raise ApifyServiceError(f"Failed to start Apify run ({resp.status_code}): {resp.text[:400]}")
                data = (resp.json() or {}).get("data") or {}
                return {
                    "apify_run_id": data.get("id"),
                    "status": data.get("status") or "READY",
                    "dataset_id": (data.get("defaultDatasetId") or None),
                    "actor_id": actor_id,
                    "raw": data,
                }
        except ApifyServiceError:
            raise
        except Exception as exc:
            raise ApifyServiceError(str(exc)) from exc

    @staticmethod
    def get_run(token: str, *, apify_run_id: str) -> dict[str, Any]:
        key = ApifyService.normalize_token(token)
        run_id = str(apify_run_id or "").strip()
        if not key or not run_id:
            raise ApifyServiceError("Apify token and run id are required")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{APIFY_API_BASE}/actor-runs/{run_id}", headers=ApifyService._headers(key))
                if resp.status_code >= 400:
                    raise ApifyServiceError(f"Failed to fetch Apify run ({resp.status_code}): {resp.text[:300]}")
                data = (resp.json() or {}).get("data") or {}
                return {
                    "apify_run_id": data.get("id") or run_id,
                    "status": data.get("status") or "UNKNOWN",
                    "dataset_id": data.get("defaultDatasetId"),
                    "started_at": data.get("startedAt"),
                    "finished_at": data.get("finishedAt"),
                    "stats": data.get("stats") or {},
                    "raw": data,
                }
        except ApifyServiceError:
            raise
        except Exception as exc:
            raise ApifyServiceError(str(exc)) from exc

    @staticmethod
    def fetch_dataset_items(token: str, *, dataset_id: str, limit: int = 500) -> list[dict[str, Any]]:
        key = ApifyService.normalize_token(token)
        ds = str(dataset_id or "").strip()
        if not key or not ds:
            raise ApifyServiceError("Apify token and dataset id are required")
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(
                    f"{APIFY_API_BASE}/datasets/{ds}/items",
                    headers=ApifyService._headers(key),
                    params={"format": "json", "clean": 1, "limit": max(1, min(int(limit or 500), 5000))},
                )
                if resp.status_code >= 400:
                    raise ApifyServiceError(f"Failed to fetch dataset ({resp.status_code}): {resp.text[:300]}")
                data = resp.json()
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    return [x for x in data["items"] if isinstance(x, dict)]
                return []
        except ApifyServiceError:
            raise
        except Exception as exc:
            raise ApifyServiceError(str(exc)) from exc

    @staticmethod
    def normalize_contact_item(item: dict[str, Any], *, expo_url: str = "", run_id: str = "") -> dict[str, Any] | None:
        """Map common Apify actor field names into AI Team prospect fields."""
        email = (
            item.get("email")
            or item.get("Email")
            or item.get("contactEmail")
            or item.get("contact_email")
            or ""
        )
        if isinstance(email, list):
            email = next((e for e in email if isinstance(e, str) and "@" in e), "")
        email = str(email or "").strip().lower()
        if not email or "@" not in email:
            # Try nested contacts
            contacts = item.get("emails") or item.get("contacts") or []
            if isinstance(contacts, list):
                for c in contacts:
                    if isinstance(c, str) and "@" in c:
                        email = c.strip().lower()
                        break
                    if isinstance(c, dict):
                        e = str(c.get("email") or c.get("value") or "").strip().lower()
                        if e and "@" in e:
                            email = e
                            break
        if not email or "@" not in email:
            return None

        first = str(item.get("first_name") or item.get("firstName") or item.get("first") or "").strip()
        last = str(item.get("last_name") or item.get("lastName") or item.get("last") or "").strip()
        name = str(item.get("name") or item.get("fullName") or item.get("contactName") or "").strip()
        if not first and name:
            parts = name.split(None, 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""

        company = str(
            item.get("company_name")
            or item.get("company")
            or item.get("companyName")
            or item.get("exhibitor")
            or item.get("organization")
            or ""
        ).strip()
        website = str(item.get("website") or item.get("url") or item.get("companyWebsite") or "").strip()
        job_title = str(item.get("job_title") or item.get("title") or item.get("jobTitle") or "Exhibitor").strip()

        return {
            "email": email,
            "first_name": first,
            "last_name": last,
            "company_name": company,
            "job_title": job_title,
            "sector": str(item.get("sector") or item.get("industry") or "expo").strip() or "expo",
            "country_code": str(item.get("country_code") or item.get("country") or "GB").strip().upper()[:8] or "GB",
            "match_score": 80,
            "source": "apify",
            "profile_json": {
                "expo_url": expo_url,
                "website": website,
                "apify_run_id": run_id,
                "raw": item,
            },
        }
