#!/usr/bin/env python3
"""Fix the Telnyx interview_email_sent template by deleting and re-syncing."""

import os
import sys
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.settings import SettingsModel

def get_api_key(db: Session) -> str | None:
    """Get Telnyx API key from settings."""
    result = db.execute(
        select(SettingsModel).where(SettingsModel.key == "telnyx_api_key")
    ).scalar_one_or_none()
    return result.value if result else None

def list_templates(api_key: str) -> list[dict]:
    """List all Telnyx WhatsApp templates."""
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            "https://api.telnyx.com/v2/whatsapp_templates",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"page[size]": 250}
        )
        response.raise_for_status()
        return response.json().get("data", [])

def delete_template(api_key: str, template_id: str) -> bool:
    """Delete a Telnyx WhatsApp template."""
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(
            f"https://api.telnyx.com/v2/whatsapp_templates/{template_id}",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        return response.status_code == 204

def main():
    # Load env
    from dotenv import load_dotenv
    load_dotenv(".env")

    # Get database connection
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/voxbulk")
    engine = create_engine(db_url)

    with Session(engine) as db:
        api_key = get_api_key(db)
        if not api_key:
            print("❌ No Telnyx API key found in settings")
            sys.exit(1)

        print("🔍 Listing Telnyx templates...")
        templates = list_templates(api_key)

        # Find interview_email_sent template
        interview_template = None
        for tmpl in templates:
            if tmpl.get("name") == "interview_email_sent":
                interview_template = tmpl
                break

        if not interview_template:
            print("❌ Template 'interview_email_sent' not found on Telnyx")
            sys.exit(1)

        print(f"✅ Found template: {interview_template['name']}")
        print(f"   ID: {interview_template['id']}")
        body_preview = interview_template.get("body_preview", interview_template.get("body", ""))
        print(f"   Body preview: {body_preview[:100]}...")

        if "{{4}}" in body_preview:
            print("\n🔴 Template still contains {{4}} 🏢 - DELETING...")
            
            if delete_template(api_key, interview_template["id"]):
                print("✅ Template deleted successfully!")
                print("\n📝 Next steps:")
                print("   1. Run the sync endpoint: POST /api/admin/integrations/telnyx/whatsapp-templates/sync")
                print("   2. Or restart the backend service to auto-sync")
            else:
                print("❌ Failed to delete template")
                sys.exit(1)
        else:
            print("✅ Template is already fixed (no {{4}} placeholder found)")

if __name__ == "__main__":
    main()
