from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/search"


class ApolloServiceError(RuntimeError):
    pass


class ApolloService:
    @staticmethod
    def test_connection(api_key: str) -> dict[str, Any]:
        key = str(api_key or "").strip()
        if not key:
            raise ApolloServiceError("Apollo API key is required")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    APOLLO_SEARCH_URL,
                    headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": key},
                    json={"page": 1, "per_page": 1, "person_titles": ["manager"]},
                )
            if resp.status_code == 401:
                raise ApolloServiceError("Invalid Apollo API key")
            if resp.status_code >= 400:
                raise ApolloServiceError(f"Apollo API error ({resp.status_code}): {resp.text[:200]}")
            data = resp.json() if resp.content else {}
            return {"ok": True, "message": "Apollo connection successful", "sample_count": len(data.get("people") or [])}
        except ApolloServiceError:
            raise
        except Exception as exc:
            raise ApolloServiceError(str(exc)) from exc

    @staticmethod
    def search_people(
        api_key: str,
        *,
        title_keywords: list[str],
        country: str | None = None,
        city_region: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        key = str(api_key or "").strip()
        if not key:
            raise ApolloServiceError("Apollo API key is not configured")

        payload: dict[str, Any] = {
            "page": 1,
            "per_page": max(1, min(int(per_page or 20), 50)),
            "person_titles": [t.strip() for t in title_keywords if t.strip()],
        }
        if country:
            payload["person_locations"] = [country.strip()]
        if city_region:
            payload["q_organization_keyword_tags"] = [city_region.strip()]

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                APOLLO_SEARCH_URL,
                headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": key},
                json=payload,
            )
        if resp.status_code >= 400:
            raise ApolloServiceError(f"Apollo search failed ({resp.status_code}): {resp.text[:300]}")

        people = (resp.json() or {}).get("people") or []
        results: list[dict[str, Any]] = []
        for person in people:
            org = person.get("organization") or {}
            email = str(person.get("email") or "").strip()
            if not email:
                continue
            results.append(
                {
                    "apollo_id": str(person.get("id") or ""),
                    "first_name": str(person.get("first_name") or "").strip(),
                    "last_name": str(person.get("last_name") or "").strip(),
                    "email": email,
                    "job_title": str(person.get("title") or "").strip(),
                    "company_name": str(org.get("name") or person.get("organization_name") or "").strip(),
                    "country_code": str((person.get("country") or org.get("country") or "GB")[:8]).upper(),
                    "profile_json": person,
                }
            )
        return results
