# Interview agent KB — upload guide

## Do you need to upload the KB?

**Two ways to load knowledge for `interview_GB-Leo`:**

| Method | When to use |
|--------|-------------|
| **A. Seed script (recommended on VPS)** | Runs once after deploy — embeds KB into the agent automatically |
| **B. Admin upload** | Attach/update KB without re-running the seed script |

You do **not** need both if the seed script ran successfully. Use **Admin upload** if you want to edit the KB later without SSH.

---

## A. VPS — seed agent + KB (after git pull)

```bash
cd /path/to/Vox   # your repo on VPS
git pull origin main
python voxbulk-api/scripts/seed_interview_gb_leo.py
./deploy-vps.sh
```

This creates/updates **interview_GB-Leo** with Telnyx ID `assistant-19b10379-bea4-4a0e-ad82-c220d0fd54fd` and loads KB text into the agent.

Optional `.env`:

```env
INTERVIEW_TELNYX_ASSISTANT_ID=assistant-19b10379-bea4-4a0e-ad82-c220d0fd54fd
```

---

## B. Admin — upload KB file manually

1. Download or copy: `voxbulk-api/kb-upload-ready/interview/interview_GB-Leo-kb.md`
2. Admin → **Main agents** → Edit **interview_GB-Leo**
3. **Knowledge base** → **Upload .md** → select the file
4. Tick the file to attach → **Save agent**

Also upload the same file to the **Telnyx assistant** portal if you want Telnyx-side RAG (optional — VoxBulk injects KB at runtime too).

---

## File location in repo

```
voxbulk-api/kb-upload-ready/interview/interview_GB-Leo-kb.md
```

Use this file for VPS testing and production.
