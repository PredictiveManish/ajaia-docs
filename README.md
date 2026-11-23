# Ajaia Docs

A small collaborative document editor: create, edit rich text, import a file, share with another user, and reopen after refresh.

Built with FastAPI, SQLite, Jinja2 and Quill. No build step, no paid dependency.

## Live demo

DEPLOY_URL_HERE

## Test accounts

Three users are seeded on first run. Password for all three: `demo123`

| Username | Display name |
|---|---|
| `manish` | Manish Tiwari |
| `priya` | Priya Sharma |
| `alex` | Alex Chen |

To see sharing: sign in as `manish`, open a document, use the Share panel to grant access to `priya`. Sign out, sign in as `priya`, and the document appears under "Shared with you".

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

The SQLite file `docs.db` is created automatically and seeded with the three users above.

## Tests

```bash
pytest -q
```

Eleven tests covering authentication enforcement, ownership enforcement, sharing grants and revocation, persistence across requests, upload validation, `.docx` import, and version-history deduplication.

## Upload size limit

Default is **10 MB**, configurable with the `MAX_UPLOAD_MB` environment variable. The reasoning is in `ARCHITECTURE.md`; the short version is that the file is read into memory and stored in a SQLite text column, and every version snapshot duplicates that content, so the limit bounds memory per request rather than being arbitrary.

Document body size has a separate cap of 5,000,000 characters on the save endpoint.

## Deploy

Any host that runs Python works. On Render:

1. New Web Service, connect the repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. Set env var `SECRET_KEY` to a long random string

**Known limitation:** on free tiers the filesystem is ephemeral, so `docs.db` resets on redeploy. For anything real, attach a persistent disk or move to Postgres. See `ARCHITECTURE.md`.

## What is supported

- Create, rename, delete documents
- Rich text: bold, italic, underline, H1/H2/H3, bulleted and numbered lists
- Autosave (1.2s after typing stops) plus Ctrl/Cmd+S
- Import `.txt`, `.md` or `.docx` as a new document (default cap 10 MB, see below)
- Share a document with another user; owned and shared are listed separately
- Revoke a share
- **Version history**: every distinct save is snapshotted, with a line-level diff against the current text and one-click restore

## What is not supported

- Real-time co-editing (no CRDT or OT)
- Concurrent-edit conflict resolution (last write wins)
- Comments, suggestion mode, PDF export
- Password reset, signup, email verification
- Side-by-side version comparison; the diff is inline against the current text only
