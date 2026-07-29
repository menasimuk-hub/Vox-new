"""Phase 9 hygiene: scripts relocated, deploy .env chmod, no full source of .env."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "voxbulk-api"


def test_secret_scripts_not_at_api_root():
    assert not (API / "get_api_key.py").exists()
    assert not (API / "fix_telnyx_template.py").exists()
    get_key = API / "scripts" / "get_api_key.py"
    fix_tpl = API / "scripts" / "fix_telnyx_template.py"
    assert get_key.is_file()
    assert fix_tpl.is_file()
    get_txt = get_key.read_text(encoding="utf-8")
    fix_txt = fix_tpl.read_text(encoding="utf-8")
    assert "NEVER run in production" in get_txt
    assert "NEVER run in production" in fix_txt
    assert "fingerprint" in get_txt.lower()
    assert 'print(f"API Key:' not in get_txt


def test_deploy_vps_chmods_env_and_avoids_full_source():
    deploy = (ROOT / "deploy-vps.sh").read_text(encoding="utf-8")
    assert "chmod 600" in deploy
    assert 'source "$env_file"' not in deploy
    # Still reads ENV= via grep rather than sourcing secrets into the shell.
    assert "grep -E '^ENV='" in deploy
