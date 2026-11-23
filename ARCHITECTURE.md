# Architecture note

## What I built

A single FastAPI process serving server-rendered pages, backed by SQLite.

```
Browser
  ├─ Quill (CDN)            rich text editing, serialises to HTML
  └─ fetch() autosave  ──►  FastAPI  ──►  SQLite (users, documents, shares)
```

**Data model.** Four tables: `users`, `documents` (owner_id, title, content, timestamps), `shares` (doc_id, user_id) as a composite-key join table, and `versions` (doc_id, content, saved_by, created_at). Access is derived, not duplicated: a document is either owned or shared, and that is computed at read time.

**Access control.** One function, `can_access(doc_id, uid)`, returns `(document, "owner" | "shared" | None)`. Every route goes through it. Write operations (rename, delete, share) require `"owner"`; read and edit accept `"shared"`. This keeps the rule in one place instead of scattered `if` statements.

**Auth.** Session cookie via Starlette's `SessionMiddleware`, signed with `SECRET_KEY`. Passwords are SHA-256 hashed. This is deliberately not production auth — see the cuts below.

**Editor.** Quill 1.3.7 from a CDN, configured with exactly the toolbar the brief asked for. Content is stored as HTML, which round-trips through the editor and renders directly on reopen.

**Saving.** Debounced autosave 1.2 seconds after the last keystroke, plus Ctrl/Cmd+S, plus a `beforeunload` guard when there are unsaved changes. The save endpoint is a JSON POST so the page never reloads mid-edit.

## Version history

Every save calls `snapshot()`, which inserts a row **only if the content differs from the most recent snapshot**. That one condition is what keeps history meaningful: without it, autosave every 1.2 seconds would produce hundreds of identical rows and the feature would be noise. History is capped at the most recent 100 versions per document.

The diff is computed server-side with `difflib.unified_diff`, not in the browser. Because content is stored as HTML, a raw line diff would compare tag soup and tell the user nothing, so `text_lines()` first flattens the HTML into readable lines by converting block-closing tags to newlines and stripping the rest. The diff is then over text the reader recognises.

Restore writes the old content back as the current document and snapshots that, so restoring is itself undoable. It is a linear history rather than a branching one, which is the right call at this scope.

**Known gap:** the diff compares each version against the *current* text, not against the version immediately before it. For a document with many saves this answers "what is different from now", which is what someone deciding whether to restore actually wants, but it is not a true commit-by-commit log.

## Upload limit, and why it is 10 MB

My first version used 1 MB, which was arbitrary. The real constraints are:

1. The upload is read fully into memory (`await file.read()`) before size is checked, so the limit bounds peak memory per request.
2. Content goes into a SQLite `TEXT` column, and SQLite rows are read whole.
3. **Every version snapshot duplicates the content**, so a 50 MB document with 100 versions is 5 GB of database.

10 MB of UTF-8 text is roughly ten million characters, about twenty novels, which is well past any realistic document while still bounding memory. It is an environment variable (`MAX_UPLOAD_MB`) rather than a constant because the right number depends on the host's memory. The document body cap on the save endpoint is separate and set at 5,000,000 characters.

## Scope decisions, and why

**Server-rendered HTML instead of React.** I had four hours and no React experience. A working editor with real persistence beats a half-wired SPA. React would be the right call with two days.

**HTML as the storage format, not a Delta or a ProseMirror doc.** HTML is readable in the database, renders without a parser, and lets the `.md`/`.txt` import write straight into the same field. The cost is that it is lossy if we ever swap editor libraries, which is an acceptable trade at this scope.

**Debounced autosave instead of explicit save plus versioning.** Users expect a document to just persist. Versioning would have been the more impressive demo and the less useful product for four hours.

**Version history over real-time collaboration.** The brief listed both as stretch. Version history was the better trade: it is a real user need that the product already implies (autosave means you cannot undo what you cannot see), and it is achievable in the budget, whereas a CRDT is more work than everything else combined.

**No real-time collaboration.** This is the largest deliberate cut. Doing it properly means a CRDT and a websocket layer, which is more work than everything else combined. I chose depth in auth, sharing and persistence instead, since those are what the brief asked to demonstrate.

**Mocked auth with seeded users.** The brief explicitly allows it. A real login flow with signup, hashing, and reset would have consumed the budget without showing anything the reviewer can't already see.

## Known limitations

**SQLite on an ephemeral filesystem.** On Render's free tier the database resets on redeploy. Fix: attach a persistent disk, or swap `db()` for Postgres behind the same interface. The SQL is plain enough that this is a contained change.

**No optimistic concurrency.** Two people editing the same document will overwrite each other; last write wins. A real version would carry an `updated_at` check on save and reject stale writes with a 409.

**History is linear, not branching.** No merge, no named checkpoints.

**HTML content is trusted on render.** It comes from the Quill editor, and file imports are escaped server-side. But there is no sanitiser on the save path, so a hostile client could store script. Fix: run `bleach` on save.

**SHA-256 with no salt** for passwords. Fine for seeded demo accounts, wrong for real ones.

## What I would build next with 2-4 more hours

1. Optimistic concurrency on save, returning 409 and reloading on conflict.
2. Bleach sanitiser on the save path.
3. Share permissions as a column (`view` | `edit`) rather than a boolean, with the UI reflecting it.
4. Postgres, so the deployment actually persists.
5. Diff each version against its immediate predecessor as well as against current, with a toggle.
