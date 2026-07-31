from __future__ import annotations

import argparse
import threading
from pathlib import Path

from .config import load_project_config
from .events import ProgressEvent
from .operations import SUPPORTED_MODES, run_project


def main() -> None:
    parser = argparse.ArgumentParser(prog="archive-scout")
    parser.add_argument("project", type=Path, help="Path to project.json")
    parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="all")
    args = parser.parse_args()
    config = load_project_config(args.project)

    def show(event: ProgressEvent) -> None:
        print(event.message, flush=True)

    paths = run_project(config, args.mode, threading.Event(), show)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
