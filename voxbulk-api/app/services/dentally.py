from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dentally_appointment import DentallyAppointment
from app.models.branch import Branch
from app.models.patient import Patient


@dataclass(frozen=True)
class DentallySyncStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class DentallyError(RuntimeError):
    pass


class DentallyAdapter:
    """Dentally adapter foundation (HTTP shape, pagination strategy)."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @classmethod
    def from_settings(cls) -> "DentallyAdapter":
        # Ensure tests / runtime env changes are respected.
        get_settings.cache_clear()
        s = get_settings()
        if not s.dentally_api_key:
            raise DentallyError("Dentally API key missing")
        return cls(base_url=s.dentally_base_url, api_key=s.dentally_api_key)

    def _headers(self) -> dict[str, str]:
        # NOTE: Header scheme may differ; kept minimal for foundation and mocked in tests.
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url, headers=self._headers(), params=params or {})
        r.raise_for_status()
        return r.json()

    def iter_paginated(self, path: str, *, params: dict[str, Any] | None = None) -> Iterable[dict[str, Any]]:
        """
        Pagination foundation: supports either:
        - response={"items":[...], "next_page": <int|str|None>}
        - response={"data":[...], "next_page": <int|str|None>}
        """
        page_params = dict(params or {})
        while True:
            payload = self._get(path, params=page_params)
            items = payload.get("items") or payload.get("data") or []
            for it in items:
                if isinstance(it, dict):
                    yield it
            nxt = payload.get("next_page")
            if not nxt:
                break
            page_params["page"] = nxt

    # Minimal scope: branches / patients / appointments
    def list_branches(self) -> list[dict[str, Any]]:
        return list(self.iter_paginated("/branches"))

    def list_patients(self) -> list[dict[str, Any]]:
        return list(self.iter_paginated("/patients"))

    def list_appointments(self) -> list[dict[str, Any]]:
        return list(self.iter_paginated("/appointments"))


class DentallySyncService:
    """Tenant-safe, idempotent upsert sync for minimal fields used by current flows."""

    @staticmethod
    def sync_branches(db: Session, *, org_id: str, adapter: DentallyAdapter) -> DentallySyncStats:
        stats = DentallySyncStats()
        for b in adapter.list_branches():
            dentally_id = str(b.get("id") or "")
            name = str(b.get("name") or "").strip()
            if not dentally_id or not name:
                stats = DentallySyncStats(stats.created, stats.updated, stats.skipped + 1, stats.failed)
                continue
            existing = db.execute(
                select(Branch).where(Branch.org_id == org_id, Branch.dentally_id == dentally_id)
            ).scalar_one_or_none()
            if existing is None:
                db.add(Branch(org_id=org_id, dentally_id=dentally_id, name=name))
                stats = DentallySyncStats(stats.created + 1, stats.updated, stats.skipped, stats.failed)
            else:
                if existing.name != name:
                    existing.name = name
                    db.add(existing)
                    stats = DentallySyncStats(stats.created, stats.updated + 1, stats.skipped, stats.failed)
                else:
                    stats = DentallySyncStats(stats.created, stats.updated, stats.skipped + 1, stats.failed)
        db.commit()
        return stats

    @staticmethod
    def sync_patients(db: Session, *, org_id: str, adapter: DentallyAdapter) -> DentallySyncStats:
        stats = DentallySyncStats()
        for p in adapter.list_patients():
            dentally_id = str(p.get("id") or "")
            first_name = str(p.get("first_name") or p.get("firstName") or "").strip()
            last_name = str(p.get("last_name") or p.get("lastName") or "").strip()
            phone = p.get("phone_e164") or p.get("phone") or None
            email = p.get("email") or None
            if not dentally_id or not first_name or not last_name:
                stats = DentallySyncStats(stats.created, stats.updated, stats.skipped + 1, stats.failed)
                continue
            existing = db.execute(
                select(Patient).where(Patient.org_id == org_id, Patient.dentally_id == dentally_id)
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    Patient(
                        org_id=org_id,
                        dentally_id=dentally_id,
                        first_name=first_name,
                        last_name=last_name,
                        phone_e164=str(phone) if phone else None,
                        email=str(email) if email else None,
                    )
                )
                stats = DentallySyncStats(stats.created + 1, stats.updated, stats.skipped, stats.failed)
            else:
                changed = False
                if existing.first_name != first_name:
                    existing.first_name = first_name
                    changed = True
                if existing.last_name != last_name:
                    existing.last_name = last_name
                    changed = True
                if (existing.phone_e164 or None) != (str(phone) if phone else None):
                    existing.phone_e164 = str(phone) if phone else None
                    changed = True
                if (existing.email or None) != (str(email) if email else None):
                    existing.email = str(email) if email else None
                    changed = True
                if changed:
                    db.add(existing)
                    stats = DentallySyncStats(stats.created, stats.updated + 1, stats.skipped, stats.failed)
                else:
                    stats = DentallySyncStats(stats.created, stats.updated, stats.skipped + 1, stats.failed)
        db.commit()
        return stats

    @staticmethod
    def sync_appointments(db: Session, *, org_id: str, adapter: DentallyAdapter) -> DentallySyncStats:
        stats = DentallySyncStats()
        for a in adapter.list_appointments():
            dentally_id = str(a.get("id") or "")
            scheduled_start = a.get("scheduled_start") or a.get("start") or None
            status = str(a.get("status") or "scheduled")
            value_raw = a.get("value_gbp_pence") or a.get("valuePence") or a.get("value_pence") or None
            reason_raw = a.get("reason") or None
            td_raw = a.get("treatment_description") or None
            patient_dentally_id = a.get("patient_id") or a.get("patientId") or None
            branch_dentally_id = a.get("branch_id") or a.get("branchId") or None
            if not dentally_id or not scheduled_start:
                stats = DentallySyncStats(stats.created, stats.updated, stats.skipped + 1, stats.failed)
                continue

            patient_id = None
            if patient_dentally_id:
                patient_id = db.execute(
                    select(Patient.id).where(Patient.org_id == org_id, Patient.dentally_id == str(patient_dentally_id))
                ).scalar_one_or_none()
            branch_id = None
            if branch_dentally_id:
                branch_id = db.execute(
                    select(Branch.id).where(Branch.org_id == org_id, Branch.dentally_id == str(branch_dentally_id))
                ).scalar_one_or_none()

            if isinstance(scheduled_start, str):
                try:
                    dt = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
                except Exception:
                    stats = DentallySyncStats(stats.created, stats.updated, stats.skipped, stats.failed + 1)
                    continue
            else:
                stats = DentallySyncStats(stats.created, stats.updated, stats.skipped, stats.failed + 1)
                continue

            existing = db.execute(
                select(DentallyAppointment).where(DentallyAppointment.org_id == org_id, DentallyAppointment.dentally_id == dentally_id)
            ).scalar_one_or_none()
            if existing is None:
                value_gbp_pence = None
                if value_raw is not None:
                    try:
                        value_gbp_pence = int(value_raw)
                    except Exception:
                        value_gbp_pence = None
                treatment_label = None
                td = str(td_raw).strip() if td_raw is not None else ""
                rsn = str(reason_raw).strip() if reason_raw is not None else ""
                if td:
                    treatment_label = td
                elif rsn:
                    treatment_label = rsn
                db.add(
                    Appointment(
                        org_id=org_id,
                        dentally_id=dentally_id,
                        patient_id=patient_id,
                        branch_id=branch_id,
                        scheduled_start=dt,
                        status=status,
                        value_gbp_pence=value_gbp_pence,
                        treatment_label=treatment_label,
                    )
                )
                stats = DentallySyncStats(stats.created + 1, stats.updated, stats.skipped, stats.failed)
            else:
                changed = False
                if existing.scheduled_start != dt:
                    existing.scheduled_start = dt
                    changed = True
                if existing.status != status:
                    existing.status = status
                    changed = True
                if existing.patient_id != patient_id:
                    existing.patient_id = patient_id
                    changed = True
                if existing.branch_id != branch_id:
                    existing.branch_id = branch_id
                    changed = True
                if value_raw is not None:
                    try:
                        v = int(value_raw)
                    except Exception:
                        v = None
                    if v is not None and existing.value_gbp_pence != v:
                        existing.value_gbp_pence = v
                        changed = True
                td = str(td_raw).strip() if td_raw is not None else ""
                rsn = str(reason_raw).strip() if reason_raw is not None else ""
                new_label = td or rsn or None
                if new_label and (existing.treatment_label or None) != new_label:
                    existing.treatment_label = new_label
                    changed = True
                if changed:
                    db.add(existing)
                    stats = DentallySyncStats(stats.created, stats.updated + 1, stats.skipped, stats.failed)
                else:
                    stats = DentallySyncStats(stats.created, stats.updated, stats.skipped + 1, stats.failed)
        db.commit()
        return stats

