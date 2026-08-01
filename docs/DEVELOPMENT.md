# Development

## Requirements

- Python 3.11 or newer
- Tkinter
- `truststore`

Install runtime requirements:

```bash
python -m pip install -r requirements-runtime.txt
```

Run the interface:

```bash
python run_app.py
```

Run all tests:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Compile-check the package:

```bash
python -m compileall -q archive_scout
```

The test workflow runs on Windows, Linux, and Intel macOS using Python 3.11 and 3.12. The build workflow creates Windows x64, Linux x64, and universal macOS packages.
