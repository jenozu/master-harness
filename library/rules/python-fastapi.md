---
paths:
  - "backend/**/*.py"
---

# Python + FastAPI rules

<!-- Library rule. Adjust the paths above to where the Python code lives in this project. -->

- Layout: routers in `routers/`, Pydantic schemas in `schemas/`, business logic in `services/`, DB models in
  `models.py` or `models/`. Keep routers thin.
- Use the project's virtualenv python (`venv/bin/python`, or `venv/Scripts/python.exe` on Windows), never the
  system one. Install with `pip install -q -r requirements.txt`; pin new deps only when a task names them.
- Type hints on new functions. Pydantic models for every request and response body.
- Auth: every endpoint touching user data depends on the current-user dependency and filters by user id;
  another user's row returns 404, not 403, so ids can't be probed.
- Raw SQL only through `sqlalchemy.text()` with bound parameters.
- Schema changes go through migrations (`db-migration` skill), never `create_all` in app code.
- `logging`, not `print`. Never log tokens, passwords or full request bodies.
- Tests: pytest + FastAPI `TestClient`, in `tests/`, against a separate test database. Run with `-q`.
- Keep `requirements.txt` UTF-8 (Windows editors sometimes save UTF-16, which breaks pip).
