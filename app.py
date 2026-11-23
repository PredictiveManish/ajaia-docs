import os, re, sqlite3, hashlib, difflib, html as htmlmod
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

DB = os.environ.get("DB_PATH", "docs.db")
SECRET = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-prod")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))   # see ARCHITECTURE.md for why
MAX_CONTENT = 5_000_000
HISTORY_KEEP = 100

app = FastAPI(title="Ajaia Docs")
app.add_middleware(SessionMiddleware, secret_key=SECRET)
templates = Jinja2Templates(directory="templates")

def hashpw(p: str) -> str: return hashlib.sha256(p.encode()).hexdigest()
def now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, display_name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS documents(
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL,
      title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shares(
      doc_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
      PRIMARY KEY(doc_id, user_id));
    CREATE TABLE IF NOT EXISTS versions(
      id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL,
      content TEXT NOT NULL, saved_by INTEGER, created_at TEXT NOT NULL);
    """)
    for u, d in [("manish","Manish Tiwari"),("priya","Priya Sharma"),("alex","Alex Chen")]:
        c.execute("INSERT OR IGNORE INTO users(username,password,display_name) VALUES(?,?,?)",
                  (u, hashpw("demo123"), d))
    # one demo document so a fresh (or reset) database is never an empty screen
    has = c.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    if not has:
        manish = c.execute("SELECT id FROM users WHERE username='manish'").fetchone()["id"]
        priya = c.execute("SELECT id FROM users WHERE username='priya'").fetchone()["id"]
        sample = ("<h1>Product notes</h1>"
                  "<p>This document is seeded so reviewers have something to open immediately.</p>"
                  "<p><strong>Try this:</strong></p>"
                  "<ul><li>Edit this text and watch the status say <em>Saved</em></li>"
                  "<li>Reload the page to confirm it persisted</li>"
                  "<li>Open <strong>History</strong> to see the diff and restore</li></ul>")
        cur = c.execute("INSERT INTO documents(owner_id,title,content,created_at,updated_at) VALUES(?,?,?,?,?)",
                        (manish, "Product notes (sample)", sample, now(), now()))
        c.execute("INSERT INTO versions(doc_id,content,saved_by,created_at) VALUES(?,?,?,?)",
                  (cur.lastrowid, sample, manish, now()))
        c.execute("INSERT OR IGNORE INTO shares(doc_id,user_id) VALUES(?,?)", (cur.lastrowid, priya))
    c.commit(); c.close()
init_db()

def current_user(request: Request):
    uid = request.session.get("uid")
    if not uid: return None
    c = db(); u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); c.close()
    return u

def LOGIN(): return RedirectResponse("/login", status_code=303)

def can_access(doc_id: int, uid: int):
    c = db()
    d = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d: c.close(); return None, None
    if d["owner_id"] == uid: c.close(); return d, "owner"
    s = c.execute("SELECT 1 FROM shares WHERE doc_id=? AND user_id=?", (doc_id, uid)).fetchone()
    c.close()
    return (d, "shared") if s else (d, None)

def snapshot(doc_id: int, content: str, uid: int):
    """Record a version only when the content actually changed, then cap history."""
    c = db()
    last = c.execute("SELECT content FROM versions WHERE doc_id=? ORDER BY id DESC LIMIT 1", (doc_id,)).fetchone()
    if not last or last["content"] != content:
        c.execute("INSERT INTO versions(doc_id,content,saved_by,created_at) VALUES(?,?,?,?)",
                  (doc_id, content, uid, now()))
        c.execute("""DELETE FROM versions WHERE doc_id=? AND id NOT IN
                     (SELECT id FROM versions WHERE doc_id=? ORDER BY id DESC LIMIT ?)""",
                  (doc_id, doc_id, HISTORY_KEEP))
        c.commit()
    c.close()

def text_lines(html_str: str):
    """Flatten stored HTML into readable lines so a diff means something to a human."""
    t = re.sub(r"<(br|/p|/li|/h[1-6])[^>]*>", "\n", html_str or "")
    t = re.sub(r"<[^>]+>", "", t)
    t = htmlmod.unescape(t)
    return [l.strip() for l in t.splitlines() if l.strip()]

def render_diff(old_html: str, new_html: str) -> str:
    a, b = text_lines(old_html), text_lines(new_html)
    rows = []
    for line in difflib.unified_diff(a, b, fromfile="this version", tofile="current", lineterm="", n=2):
        if line.startswith("+++") or line.startswith("---"): continue
        if line.startswith("@@"):
            rows.append(f'<div class="dl hunk">{htmlmod.escape(line)}</div>')
        elif line.startswith("+"):
            rows.append(f'<div class="dl add">+ {htmlmod.escape(line[1:])}</div>')
        elif line.startswith("-"):
            rows.append(f'<div class="dl del">- {htmlmod.escape(line[1:])}</div>')
        else:
            rows.append(f'<div class="dl ctx">&nbsp;&nbsp;{htmlmod.escape(line[1:])}</div>')
    return "".join(rows) if rows else '<div class="dl ctx">No textual differences.</div>'

@app.get("/health")
def health(): return {"ok": True}

@app.get("/")
def home(request: Request):
    return RedirectResponse("/documents" if current_user(request) else "/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    c = db()
    u = c.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    c.close()
    if not u or u["password"] != hashpw(password):
        return templates.TemplateResponse(request, "login.html",
            {"error": "Wrong username or password."}, status_code=401)
    request.session["uid"] = u["id"]
    return RedirectResponse("/documents", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie("session")
    return r

@app.get("/documents", response_class=HTMLResponse)
def list_docs(request: Request):
    u = current_user(request)
    if not u: return LOGIN()
    c = db()
    owned = c.execute("SELECT * FROM documents WHERE owner_id=? ORDER BY updated_at DESC", (u["id"],)).fetchall()
    shared = c.execute("""SELECT d.*, us.display_name AS owner_name FROM documents d
        JOIN shares s ON s.doc_id=d.id JOIN users us ON us.id=d.owner_id
        WHERE s.user_id=? ORDER BY d.updated_at DESC""", (u["id"],)).fetchall()
    c.close()
    return templates.TemplateResponse(request, "index.html",
        {"user": u, "owned": owned, "shared": shared, "max_mb": MAX_UPLOAD_MB})

@app.post("/documents")
def create_doc(request: Request, title: str = Form("Untitled document")):
    u = current_user(request)
    if not u: return LOGIN()
    t = (title or "").strip()[:200] or "Untitled document"
    c = db()
    cur = c.execute("INSERT INTO documents(owner_id,title,content,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (u["id"], t, "", now(), now()))
    did = cur.lastrowid; c.commit(); c.close()
    return RedirectResponse(f"/documents/{did}", status_code=303)

@app.get("/documents/{doc_id}", response_class=HTMLResponse)
def open_doc(request: Request, doc_id: int):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d: raise HTTPException(404, "Document not found")
    if not role: raise HTTPException(403, "You do not have access to this document")
    c = db()
    others = c.execute("SELECT id, display_name FROM users WHERE id!=?", (u["id"],)).fetchall()
    shared_with = c.execute("""SELECT u.id, u.display_name FROM shares s
        JOIN users u ON u.id=s.user_id WHERE s.doc_id=?""", (doc_id,)).fetchall()
    nver = c.execute("SELECT COUNT(*) AS n FROM versions WHERE doc_id=?", (doc_id,)).fetchone()["n"]
    c.close()
    return templates.TemplateResponse(request, "editor.html",
        {"user": u, "doc": d, "role": role, "others": others,
         "shared_with": shared_with, "nver": nver})

@app.post("/documents/{doc_id}/save")
async def save_doc(request: Request, doc_id: int):
    u = current_user(request)
    if not u: return JSONResponse({"ok": False, "error": "not logged in"}, status_code=401)
    d, role = can_access(doc_id, u["id"])
    if not d or not role: raise HTTPException(403, "No access")
    body = await request.json()
    content = body.get("content", "")
    if len(content) > MAX_CONTENT: raise HTTPException(413, "Document too large")
    c = db()
    c.execute("UPDATE documents SET content=?, updated_at=? WHERE id=?", (content, now(), doc_id))
    c.commit(); c.close()
    snapshot(doc_id, content, u["id"])
    return {"ok": True, "saved_at": now()}

@app.post("/documents/{doc_id}/rename")
def rename_doc(request: Request, doc_id: int, title: str = Form(...)):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d or role != "owner": raise HTTPException(403, "Only the owner can rename")
    t = title.strip()[:200]
    if not t: raise HTTPException(400, "Title cannot be empty")
    c = db(); c.execute("UPDATE documents SET title=?, updated_at=? WHERE id=?", (t, now(), doc_id))
    c.commit(); c.close()
    return RedirectResponse(f"/documents/{doc_id}", status_code=303)

@app.post("/documents/{doc_id}/delete")
def delete_doc(request: Request, doc_id: int):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d or role != "owner": raise HTTPException(403, "Only the owner can delete")
    c = db()
    c.execute("DELETE FROM shares WHERE doc_id=?", (doc_id,))
    c.execute("DELETE FROM versions WHERE doc_id=?", (doc_id,))
    c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    c.commit(); c.close()
    return RedirectResponse("/documents", status_code=303)

@app.post("/documents/{doc_id}/share")
def share_doc(request: Request, doc_id: int, user_id: int = Form(...)):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d or role != "owner": raise HTTPException(403, "Only the owner can share")
    if user_id == u["id"]: raise HTTPException(400, "You already own this document")
    c = db()
    if not c.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone():
        c.close(); raise HTTPException(400, "Unknown user")
    c.execute("INSERT OR IGNORE INTO shares(doc_id,user_id) VALUES(?,?)", (doc_id, user_id))
    c.commit(); c.close()
    return RedirectResponse(f"/documents/{doc_id}", status_code=303)

@app.post("/documents/{doc_id}/unshare")
def unshare_doc(request: Request, doc_id: int, user_id: int = Form(...)):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d or role != "owner": raise HTTPException(403, "Only the owner can change sharing")
    c = db(); c.execute("DELETE FROM shares WHERE doc_id=? AND user_id=?", (doc_id, user_id))
    c.commit(); c.close()
    return RedirectResponse(f"/documents/{doc_id}", status_code=303)

@app.get("/documents/{doc_id}/history", response_class=HTMLResponse)
def history(request: Request, doc_id: int):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d or not role: raise HTTPException(403, "No access")
    c = db()
    vers = c.execute("""SELECT v.*, us.display_name AS who FROM versions v
        LEFT JOIN users us ON us.id=v.saved_by
        WHERE v.doc_id=? ORDER BY v.id DESC LIMIT 30""", (doc_id,)).fetchall()
    c.close()
    out = []
    for v in vers:
        out.append({**dict(v), "diff": render_diff(v["content"], d["content"]),
                    "is_current": v["content"] == d["content"]})
    return templates.TemplateResponse(request, "history.html",
        {"user": u, "doc": d, "role": role, "versions": out})

@app.post("/documents/{doc_id}/restore/{vid}")
def restore(request: Request, doc_id: int, vid: int):
    u = current_user(request)
    if not u: return LOGIN()
    d, role = can_access(doc_id, u["id"])
    if not d or not role: raise HTTPException(403, "No access")
    c = db()
    v = c.execute("SELECT content FROM versions WHERE id=? AND doc_id=?", (vid, doc_id)).fetchone()
    if not v: c.close(); raise HTTPException(404, "Version not found")
    c.execute("UPDATE documents SET content=?, updated_at=? WHERE id=?", (v["content"], now(), doc_id))
    c.commit(); c.close()
    snapshot(doc_id, v["content"], u["id"])
    return RedirectResponse(f"/documents/{doc_id}", status_code=303)

@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    u = current_user(request)
    if not u: return LOGIN()
    name = (file.filename or "").lower()
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB} MB)")
    title = os.path.splitext(file.filename or "Imported")[0][:200] or "Imported document"

    if name.endswith(".docx"):
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(raw))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            body = "".join(f"<p>{htmlmod.escape(p)}</p>" for p in parts)
        except ImportError:
            raise HTTPException(400, "DOCX support unavailable on this host; use .txt or .md")
        except Exception:
            raise HTTPException(400, "Could not read that .docx file")
    elif name.endswith(".txt") or name.endswith(".md"):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "File must be UTF-8 text")
        body = "".join(f"<p>{htmlmod.escape(l)}</p>" for l in text.splitlines() if l.strip())
    else:
        raise HTTPException(400, "Supported types: .txt, .md, .docx")

    c = db()
    cur = c.execute("INSERT INTO documents(owner_id,title,content,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (u["id"], title, body, now(), now()))
    did = cur.lastrowid; c.commit(); c.close()
    snapshot(did, body, u["id"])
    return RedirectResponse(f"/documents/{did}", status_code=303)
