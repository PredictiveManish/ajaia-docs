# Submission

**Candidate:** Manish Tiwari
**Role:** AI-Native Full Stack Developer

## Included in this folder

| Item | File |
|---|---|
| Source code | `app.py`, `templates/` |
| Tests | `test_app.py` |
| Dependencies | `requirements.txt` |
| Setup and run instructions | `README.md` |
| Architecture note | `ARCHITECTURE.md` |
| AI workflow note | `AI_WORKFLOW.md` |
| This manifest | `SUBMISSION.md` |
| Walkthrough video | `VIDEO_URL.txt` |

## Live deployment

DEPLOY_URL_HERE

## Test accounts

Password `demo123` for all three: `manish`, `priya`, `alex`.

To test sharing: sign in as `manish`, open a document, share with `priya`, sign out, sign in as `priya`.

## What is working

- Document create, rename, delete
- Rich text editing: bold, italic, underline, H1-H3, bulleted and numbered lists
- Autosave plus manual save, persistence across refresh
- `.txt`, `.md` and `.docx` import as a new document
- Sharing with an owner/shared distinction, and revocation
- Version history with line-level diffs against current text, and restore
- Export to PDF with headings, bold, italic and lists preserved
- 13 automated tests, all passing

## What is incomplete

- No real-time collaboration or conflict resolution. Last write wins.
- Share is boolean access, not view/edit roles.
- History is linear and compares against current text, not version-to-version.
- No comments or suggestion mode.
- PDF export uses Latin-1 core fonts, so Indic scripts do not render yet.
- Passwords are SHA-256 with no salt; this is demo auth, not production auth.
- SQLite on a free-tier host resets on redeploy. Documented in `ARCHITECTURE.md`.

## With another 2-4 hours

1. Embed a Unicode TTF so PDF export handles Indic scripts.
2. Optimistic concurrency: send `updated_at` with each save, return 409 on a stale write, reload on conflict.
3. `bleach` sanitiser on the HTML save path.
4. Postgres so the deployment actually persists.
5. Share permissions as `view` / `edit` with the UI reflecting the difference.
