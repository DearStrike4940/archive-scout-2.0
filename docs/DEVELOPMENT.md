# Development

## Requirements

- Python 3.11 or newer
- Tk support
- `truststore`
- PyInstaller only when building desktop packages

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-build.txt
python run_app.py
```

On Windows, activate with `.venv\Scripts\activate`.

## Tests

```bash
python -m compileall -q archive_scout
python -m unittest discover -s tests -p "test_*.py" -v
```

Tests must not make live Wayback Machine requests. Network behavior should be mocked or supplied with fixtures.

## Build scripts

```text
scripts/build_windows.ps1
scripts/build_linux.sh
scripts/build_macos.sh
```

PyInstaller must run on the operating system it is packaging. The GitHub workflow performs all three builds and publishes them together when a version tag is pushed.
