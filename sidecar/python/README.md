# cayascribe-sidecar

Loopback FastAPI process. Audio never leaves the machine.

Docs: repository [README](../../README.md) (English) · [README.tr.md](../../README.tr.md).


```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
$env:CAYA_TOKEN = "dev"
.\.venv\Scripts\python -m cayascribe.server --host 127.0.0.1 --port 8765
```
