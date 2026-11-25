# Python Style Guidelines (`src/host/`, `src/test/`, CPython host code)

- **Always prefer `pathlib.Path` over `os.path`**:
  - Use `Path(__file__).resolve().parents[...]` instead of nested `os.path.dirname(os.path.abspath(__file__))` calls.
  - Use `/` for path joining, `.mkdir(parents=True, exist_ok=True)` instead of `os.makedirs(..., exist_ok=True)`, `.exists()`, and `.open(...)` / `.read_text()` / `.write_text()`.
  - Accept `str | Path` on public helper parameters where callers may pass either (e.g., `tempfile.TemporaryDirectory()`).
  - **Exception (Pybricks Hubs)**: Hub-executed MicroPython code under `src/robot/`, `src/run_*.py`, and runtime hub paths in `src/shared/` cannot use `pathlib` (see [pybricks-micropython.md](pybricks-micropython.md)). Only use `pathlib.Path` inside CPython-only modules or guarded host-only branches (`try: from pathlib import Path ... except ImportError:`).
