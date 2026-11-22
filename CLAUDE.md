# CLAUDE.md

Lanternfish (project 007): macOS menu bar app showing Claude and Codex subscription usage. Python 3.12 + rumps; no other runtime dependencies.

## Commands
```bash
.venv/bin/pytest -q              # tests (fixtures in tests/fixtures, no network)
.venv/bin/lanternfish            # print usage once
.venv/bin/python -m lanternfish  # run the menu bar app
```

## Layout
- `src/lanternfish/providers/` — one module per source, each with `parse(data) -> Usage` (pure, tested on fixtures) and `fetch()`; failures raise `ProviderError`. Register new ones in `providers/__init__.py` `PROVIDERS`.
- `providers/__init__.py` `fetch_all()` isolates failures: one broken provider becomes a `Usage` with `.error`, never an exception.
- `format.py` — all user-visible text; `app.py` — rumps UI only (fetches on a worker thread, applies results on the main thread).

## Rules
- Endpoints are unofficial; verify the response shape with curl before changing a parser, and refresh the fixture.
- Fixtures must not contain emails, user ids or account ids (the repo is public). Never commit tokens.
- Keep the UI English and minimal; no unrequested features.
- rumps keys menu items by title: always assign items with explicit keys (`self.menu[key] = ...`).
