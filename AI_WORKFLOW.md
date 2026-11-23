# AI workflow note

## Tools

Claude (chat) for design and code generation, plus the editor's own autocomplete for boilerplate. No agentic coding tool was left to run unsupervised.

## Where AI materially sped things up

- **The Jinja templates and CSS.** I described the three screens and the visual register; it produced usable markup in one pass. That was roughly 45 minutes of work I did not do.
- **The pytest suite.** I listed the six behaviours I wanted covered and it wrote the fixtures and assertions. I then had to fix two of them (below).
- **The SQLite schema and the `can_access` helper.** The shape was my decision, the code was largely generated.
- **Quill wiring.** The CDN setup, toolbar config and the autosave debounce came back close to correct.

## What AI produced that I changed or rejected

This is the part worth reading, because it is where the four hours actually went.

**1. FastAPI was already serving `/docs`.** I had mounted the document list at `/docs`, and FastAPI's built-in Swagger UI owns that path. My route never executed. Nothing about the generated code was wrong in isolation, and the AI never flagged it. A failing test caught it: an unauthenticated request to `/docs` returned `200` instead of a redirect. I renamed everything to `/documents`.

**2. The Starlette `TemplateResponse` signature.** Generated code used the old `TemplateResponse(name, {"request": request, ...})` form. The installed version wants `TemplateResponse(request, name, context)`. The failure surfaced as `TypeError: unhashable type: 'dict'` inside Jinja's cache, which is a misleading trace for a calling-convention problem. Fixed across four call sites.

**3. Raising `HTTPException(303)` to redirect.** This looked reasonable and did not redirect. I replaced it with an explicit `RedirectResponse` returned from the route, which is also easier to read.

**4. A module-level `RedirectResponse` reused across requests.** My own error, introduced while fixing the above: I hoisted the redirect into a constant and every request shared one response object. Changed to a factory function.

**5. Logout did not clear the session.** `request.session.clear()` alone left the cookie in place under this Starlette version. Added an explicit `delete_cookie("session")` on the response.

**6. Two Jinja templates missing `{% endblock %}`.** Rewritten page shells came back syntactically incomplete. Caught by a `TemplateSyntaxError` the first time the history page rendered in a test, not at startup, which is why the tests existed before the pages did.

**7. Session-cookie leakage in the tests.** The first version of the auth test logged out and then asserted a redirect, but the cookie survived, so it was really testing nothing. Rewritten to use a fresh `TestClient` with no cookie jar, which is the actual unauthenticated case.

## How I verified correctness

- **`pytest`, eleven tests, all passing.** They cover: health, unauthenticated access redirects, wrong password rejected, create-save-reopen persistence, sharing grants access to a non-owner, non-owner cannot delete, unsupported upload rejected, markdown import creates a document, history records distinct versions without duplicating identical saves, `.docx` import works, and a shared user can read history.
- **Manual pass through the real flow**: sign in as `manish`, create, format with every toolbar button, reload and confirm formatting survives, share with `priya`, sign out, sign in as `priya`, confirm it appears under "Shared with you" and is editable, confirm `priya` cannot delete it.
- **Deliberate negative checks**: open a document ID that does not exist (404), open one not shared with me (403), upload a `.exe` (400), upload a non-UTF-8 file (400).

## Where I chose not to use AI

The access-control model, the scope cuts, the decision to drop real-time collaboration, and the choice to build version history instead were mine. Those are the judgement calls the brief is asking about, and outsourcing them would have defeated the exercise.
