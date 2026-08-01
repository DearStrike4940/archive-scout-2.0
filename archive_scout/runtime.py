from __future__ import annotations

import os
import sys
from pathlib import Path


class FrozenBundleError(RuntimeError):
    """Raised when a frozen application bundle is missing required runtime files."""


def _exception_chain(exc: BaseException):
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        reason = getattr(current, "reason", None)
        if isinstance(reason, BaseException) and reason is not current:
            current = reason
            continue
        current = current.__cause__ or current.__context__


def is_missing_frozen_bundle_error(exc: BaseException) -> bool:
    for current in _exception_chain(exc):
        filename = getattr(current, "filename", None)
        text = " ".join(part for part in (str(filename or ""), str(current)) if part).lower()
        if "base_library.zip" in text:
            return True
        if isinstance(current, FileNotFoundError) and (
            "contents/frameworks" in text or "contents/resources" in text
        ):
            return True
    return False


def frozen_bundle_runtime_path() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    value = getattr(sys, "_MEIPASS", None)
    if not value:
        return None
    return Path(value)


def macos_app_bundle_path() -> Path | None:
    if sys.platform != "darwin":
        return None
    executable = Path(sys.executable)
    for candidate in (executable, *executable.parents):
        if candidate.suffix.lower() == ".app":
            return candidate
    return None


def frozen_bundle_problem() -> str | None:
    runtime_path = frozen_bundle_runtime_path()
    if runtime_path is None:
        if getattr(sys, "frozen", False):
            return "the frozen application runtime directory is unavailable"
        return None

    executable = Path(sys.executable)
    if not executable.exists():
        return f"the application executable is no longer available at {executable}"
    if not runtime_path.exists():
        return f"the application runtime directory is no longer available at {runtime_path}"

    base_library = runtime_path / "base_library.zip"
    if not os.path.lexists(base_library):
        return f"the bundled Python library is missing at {base_library}"
    if not base_library.exists():
        return f"the bundled Python library link is broken at {base_library}"
    if not base_library.is_file():
        return f"the bundled Python library is not a file at {base_library}"

    if sys.platform == "darwin":
        bundle = macos_app_bundle_path()
        if bundle is None:
            return "the running macOS application bundle could not be located"
        if not bundle.exists():
            return f"the running application bundle is no longer available at {bundle}"

    return None


def frozen_bundle_message(detail: str | None = None) -> str:
    problem = detail or "a required bundled runtime file became unavailable"
    return (
        "Archive Scout cannot continue because "
        + problem
        + ".\n\nQuit Archive Scout completely, remove this application copy, then install a fresh copy "
        "from the release DMG into /Applications. Do not move, rename, delete, or replace the .app "
        "while it is running. Your Archive Scout project folder and database are not affected."
    )


def ensure_frozen_bundle_available() -> None:
    problem = frozen_bundle_problem()
    if problem:
        raise FrozenBundleError(frozen_bundle_message(problem))


def frozen_bundle_error_from_exception(exc: BaseException) -> FrozenBundleError:
    return FrozenBundleError(frozen_bundle_message(str(exc)))
