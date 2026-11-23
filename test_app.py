"""Meaningful tests: auth is enforced, ownership is enforced, sharing actually grants access."""
import os, tempfile, importlib
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["SECRET_KEY"] = "test-secret"
import app as appmod
from fastapi.testclient import TestClient

client = TestClient(appmod.app, follow_redirects=False)

def login(username, password="demo123"):
    r = client.post("/login", data={"username": username, "password": password})
    assert r.status_code == 303, f"login failed for {username}"

def logout():
    client.get("/logout")

def test_health():
    assert client.get("/health").json() == {"ok": True}

def test_documents_require_login():
    # fresh client = no session cookie at all, the real unauthenticated case
    fresh = TestClient(appmod.app, follow_redirects=False)
    r = fresh.get("/documents")
    assert r.status_code == 303 and r.headers["location"] == "/login"

def test_bad_password_rejected():
    fresh = TestClient(appmod.app, follow_redirects=False)
    r = fresh.post("/login", data={"username": "manish", "password": "wrong"})
    assert r.status_code == 401
    return
    logout()
    r = client.post("/login", data={"username": "manish", "password": "wrong"})
    assert r.status_code == 401

def test_create_edit_and_persist():
    logout(); login("manish")
    r = client.post("/documents", data={"title": "Quarterly plan"})
    assert r.status_code == 303
    doc_url = r.headers["location"]
    doc_id = doc_url.rsplit("/", 1)[-1]
    r = client.post(f"/documents/{doc_id}/save", json={"content": "<p><strong>Bold</strong> plan</p>"})
    assert r.status_code == 200 and r.json()["ok"] is True
    # reopen and confirm it persisted
    r = client.get(doc_url)
    assert r.status_code == 200 and "Bold" in r.text

def test_sharing_grants_access_and_non_shared_is_forbidden():
    logout(); login("manish")
    doc_id = client.post("/documents", data={"title": "Shared doc"}).headers["location"].rsplit("/", 1)[-1]
    # find priya's id
    html = client.get("/documents").text
    # priya cannot open it yet
    logout(); login("priya")
    assert client.get(f"/documents/{doc_id}").status_code == 403
    # manish shares with priya (id 2 from seed order)
    logout(); login("manish")
    assert client.post(f"/documents/{doc_id}/share", data={"user_id": 2}).status_code == 303
    logout(); login("priya")
    assert client.get(f"/documents/{doc_id}").status_code == 200

def test_non_owner_cannot_delete():
    logout(); login("priya")
    r = client.post("/documents/1/delete")
    assert r.status_code == 403

def test_upload_rejects_unsupported_type():
    logout(); login("manish")
    r = client.post("/upload", files={"file": ("bad.exe", b"nope", "application/octet-stream")})
    assert r.status_code == 400

def test_upload_markdown_creates_document():
    logout(); login("manish")
    r = client.post("/upload", files={"file": ("notes.md", b"# Title\n\nSome text", "text/markdown")})
    assert r.status_code == 303

def test_history_records_versions_and_restore_works():
    logout(); login("manish")
    doc_id = client.post("/documents", data={"title": "Versioned"}).headers["location"].rsplit("/",1)[-1]
    client.post(f"/documents/{doc_id}/save", json={"content": "<p>first draft</p>"})
    client.post(f"/documents/{doc_id}/save", json={"content": "<p>second draft</p>"})
    r = client.get(f"/documents/{doc_id}/history")
    assert r.status_code == 200 and "first draft" in r.text and "second draft" in r.text
    # identical save must not create a duplicate version
    client.post(f"/documents/{doc_id}/save", json={"content": "<p>second draft</p>"})
    from app import db
    c = db(); n = c.execute("SELECT COUNT(*) n FROM versions WHERE doc_id=?", (doc_id,)).fetchone()["n"]; c.close()
    assert n == 2, f"expected 2 distinct versions, got {n}"

def test_docx_upload_creates_document():
    import io
    from docx import Document
    buf = io.BytesIO()
    d = Document(); d.add_paragraph("Imported from Word"); d.save(buf)
    buf.seek(0)
    logout(); login("manish")
    r = client.post("/upload", files={"file": ("report.docx", buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 303
    assert "Imported from Word" in client.get(r.headers["location"]).text

def test_shared_user_can_view_history():
    logout(); login("manish")
    doc_id = client.post("/documents", data={"title": "Hist shared"}).headers["location"].rsplit("/",1)[-1]
    client.post(f"/documents/{doc_id}/save", json={"content": "<p>visible</p>"})
    client.post(f"/documents/{doc_id}/share", data={"user_id": 2})
    logout(); login("priya")
    assert client.get(f"/documents/{doc_id}/history").status_code == 200
