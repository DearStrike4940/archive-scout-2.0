from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.parse
import webbrowser
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..cdx.parameters import build_cdx_params, cdx_year_window
from ..config import KeywordSetConfig, MediaConfig, ProjectConfig, load_project_config, save_project_config
from ..constants import APP_NAME, CDX_URL, DEFAULT_IMAGE_EXTENSIONS, DEFAULT_VIDEO_EXTENSIONS, OPERATION_MODES, REVIEW_STATUSES, SCOPE_LABELS, VERSION
from ..database.connection import open_database
from ..database.repositories import (
    delete_scan_run,
    ignore_errors,
    list_errors,
    list_scan_runs,
    rename_scan_run,
    result_rows,
    save_note,
    set_match_tags,
    set_review,
)
from ..defaults import PRESETS
from ..downloads.downloader import replay_url
from ..events import ProgressEvent, Stopped
from ..operations import run_project
from ..reports.compare import generate_scan_comparison
from ..reports.export import export_review_package, export_scan
from ..reports.text import generate_reports
from ..runtime import FrozenBundleError, ensure_frozen_bundle_available
from ..scanning.full_text import search_documents

MODE_LABELS = OPERATION_MODES
MODE_HELP = {
    "all": "Queries CDX, downloads pending text captures, scans every selected keyword set, and writes reports.",
    "index": "Queries CDX and stores capture metadata without downloading pages.",
    "download": "Downloads pending text captures and scans them with every selected keyword set.",
    "resume": "Continues interrupted pending work without automatically retrying earlier errors.",
    "rescan": "Reads saved files locally and creates new scan runs without making Wayback requests.",
    "retry_errors": "Retries unresolved text-page and media errors. Valid local text files are rescanned before redownloading.",
    "report": "Recreates reports from the latest completed scan without downloading or rescanning.",
    "integrity": "Checks saved files and database links without deleting project data.",
    "media_all": "Indexes and downloads the selected image and video extensions.",
    "media_index": "Indexes selected image and video URLs without downloading the files.",
    "media_download": "Downloads pending media records already stored in this project.",
    "media_retry": "Retries only unresolved media download errors.",
}
REVIEW_LABELS = {
    "Unreviewed": "unreviewed",
    "Relevant": "relevant",
    "Possibly relevant": "possibly_relevant",
    "False positive": "false_positive",
    "Duplicate": "duplicate",
    "Dead end": "dead_end",
    "Needs follow-up": "needs_follow_up",
}


def app_support_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "archive-scout"


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))
    else:
        for command in ("xdg-open", "gio"):
            if shutil.which(command):
                subprocess.Popen([command, str(path)] if command == "xdg-open" else [command, "open", str(path)])
                return
        raise RuntimeError("No desktop file opener was found: " + str(path))


class ArchiveScoutApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1180x820")
        self.minsize(940, 680)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.last_paths: dict[str, Path] = {}
        self.keyword_sets: list[dict] = []
        self.current_keyword_set = -1
        self.scan_run_map: dict[str, int] = {}
        self.result_row_map: dict[str, dict] = {}
        self.error_row_map: dict[str, dict] = {}
        self.result_sort_column = "score"
        self.result_sort_reverse = True
        self.create_variables()
        self.create_ui()
        self.load_app_state()
        self.after(100, self.process_events)

    def create_variables(self) -> None:
        default_output = Path.home() / "Downloads" / "ArchiveScout"
        cpu_count = os.cpu_count() or 4
        self.output_var = tk.StringVar(value=str(default_output))
        self.preset_var = tk.StringVar(value="Ogrish 9/11 research")
        self.mode_var = tk.StringVar(value="Index, download, scan, and report")
        self.operation_help_var = tk.StringVar(value=MODE_HELP["all"])
        self.scope_var = tk.StringVar(value="All archived text pages (thorough)")
        self.from_date_var = tk.StringVar(value="2001")
        self.to_date_var = tk.StringVar(value="2010")
        self.cdx_match_type_var = tk.StringVar(value="Automatic")
        self.collapse_urlkey_var = tk.BooleanVar(value=True)
        self.collapse_digest_var = tk.BooleanVar(value=False)
        self.page_size_var = tk.StringVar(value="5000")
        self.workers_var = tk.StringVar(value=str(min(6, max(2, cpu_count))))
        self.max_file_var = tk.StringVar(value="25")
        self.minimum_score_var = tk.StringVar(value="1")
        self.cdx_delay_var = tk.StringVar(value="0.8")
        self.download_delay_var = tk.StringVar(value="0.25")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.keyword_set_var = tk.StringVar()
        self.keyword_set_selected_var = tk.BooleanVar(value=True)
        self.media_enabled_var = tk.BooleanVar(value=False)
        self.media_images_var = tk.BooleanVar(value=True)
        self.media_videos_var = tk.BooleanVar(value=True)
        self.media_embedded_var = tk.BooleanVar(value=True)
        self.media_external_var = tk.BooleanVar(value=False)
        self.media_strategy_var = tk.StringVar(value="earliest")
        self.media_max_var = tk.StringVar(value="500")
        self.media_preserve_var = tk.BooleanVar(value=True)
        self.result_scan_var = tk.StringVar()
        self.result_filter_var = tk.StringVar()
        self.result_review_filter_var = tk.StringVar(value="All")
        self.result_min_var = tk.StringVar(value="1")
        self.review_status_var = tk.StringVar(value="Unreviewed")
        self.review_tags_var = tk.StringVar()
        self.fts_query_var = tk.StringVar()
        self.fts_field_var = tk.StringVar(value="all")
        self.fts_domain_var = tk.StringVar()
        self.error_category_var = tk.StringVar(value="All")

    def create_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        header = ttk.Frame(self, padding=(14, 12, 14, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=APP_NAME, font=("TkDefaultFont", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Search, rescan, review, and recover public Wayback Machine material in one project.").grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(header, text="Preset:").grid(row=0, column=1, sticky="e", padx=(20, 6))
        preset = ttk.Combobox(header, textvariable=self.preset_var, values=list(PRESETS), state="readonly", width=24)
        preset.grid(row=0, column=2, sticky="e")
        preset.bind("<<ComboboxSelected>>", lambda _event: self.apply_preset())

        project = ttk.LabelFrame(self, text="Project", padding=10)
        project.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        project.columnconfigure(1, weight=1)
        ttk.Label(project, text="Output folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(project, textvariable=self.output_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(project, text="Browse…", command=self.choose_output).grid(row=0, column=2)
        ttk.Button(project, text="Open", command=self.open_output).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(project, text="Operation:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        operation = ttk.Combobox(project, textvariable=self.mode_var, values=list(MODE_LABELS), state="readonly")
        operation.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(8, 0))
        operation.bind("<<ComboboxSelected>>", lambda _event: self.update_operation_help())
        ttk.Label(project, textvariable=self.operation_help_var, wraplength=980).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=14, pady=6)
        self.create_targets_tab()
        self.create_keywords_tab()
        self.create_cdx_tab()
        self.create_media_tab()
        self.create_settings_tab()
        self.create_results_tab()
        self.create_history_tab()
        self.create_errors_tab()
        self.create_activity_tab()

        footer = ttk.Frame(self, padding=(14, 8, 14, 14))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(footer, text="Start", command=self.start)
        self.start_button.grid(row=0, column=0)
        self.stop_button = ttk.Button(footer, text="Stop", command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(footer, text="Save project", command=self.save_project).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(footer, text="Load project…", command=self.load_project).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(footer, text="Open reports", command=self.open_reports).grid(row=0, column=4, padx=(8, 0))
        self.progress = ttk.Progressbar(footer, variable=self.progress_var, maximum=100)
        self.progress.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(10, 4))
        ttk.Label(footer, textvariable=self.status_var).grid(row=2, column=0, columnspan=5, sticky="w")
        self.apply_preset()

    def create_targets_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self.notebook.add(tab, text="Sites and paths")
        ttk.Label(tab, text="One Wayback target per line. Examples: example.com/* or forum.example.com/path/*").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.targets_text = tk.Text(tab, wrap="none", undo=True, font="TkFixedFont")
        self.targets_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.targets_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.targets_text.configure(yscrollcommand=scroll.set)

    def create_keywords_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Keyword sets")
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Set:").grid(row=0, column=0)
        self.keyword_set_box = ttk.Combobox(controls, textvariable=self.keyword_set_var, state="readonly")
        self.keyword_set_box.grid(row=0, column=1, sticky="ew", padx=6)
        self.keyword_set_box.bind("<<ComboboxSelected>>", self.switch_keyword_set)
        ttk.Checkbutton(controls, text="Use in next scan", variable=self.keyword_set_selected_var, command=self.save_current_keyword_set).grid(row=0, column=2, padx=6)
        ttk.Button(controls, text="New", command=self.new_keyword_set).grid(row=0, column=3, padx=2)
        ttk.Button(controls, text="Duplicate", command=self.duplicate_keyword_set).grid(row=0, column=4, padx=2)
        ttk.Button(controls, text="Delete", command=self.delete_keyword_set).grid(row=0, column=5, padx=2)
        ttk.Button(controls, text="Import…", command=self.import_keyword_set).grid(row=0, column=6, padx=2)
        ttk.Button(controls, text="Export…", command=self.export_keyword_set).grid(row=0, column=7, padx=2)
        ttk.Label(
            tab,
            text="One rule per line. Prefixes: required:, exclude:, exact:, regex:, high:. Options: | weight=3 | whole | case | label=Name",
            wraplength=1000,
        ).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.keywords_text = tk.Text(tab, wrap="none", undo=True, font="TkFixedFont")
        self.keywords_text.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.keywords_text.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.keywords_text.configure(yscrollcommand=scroll.set)

    def create_cdx_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(6, weight=1)
        self.notebook.add(tab, text="CDX options")
        ttk.Label(tab, text="Start date:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.from_date_var, width=22).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(tab, text="End date:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.to_date_var, width=22).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(tab, text="Accepted: YYYY, YYYYMM, YYYYMMDD, or YYYYMMDDhhmmss.").grid(row=2, column=1, sticky="w", padx=(10, 0))
        ttk.Label(tab, text="matchType:").grid(row=3, column=0, sticky="w", pady=(10, 4))
        ttk.Combobox(tab, textvariable=self.cdx_match_type_var, values=("Automatic", "exact", "prefix", "host", "domain"), state="readonly", width=19).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(10, 4))
        collapse = ttk.Frame(tab)
        collapse.grid(row=4, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Checkbutton(collapse, text="collapse=urlkey", variable=self.collapse_urlkey_var).grid(row=0, column=0)
        ttk.Checkbutton(collapse, text="collapse=digest", variable=self.collapse_digest_var).grid(row=0, column=1, padx=(18, 0))
        ttk.Label(tab, text="Results per CDX page:").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.page_size_var, width=22).grid(row=5, column=1, sticky="w", padx=(10, 0), pady=4)
        options = ttk.Frame(tab)
        options.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)
        options.rowconfigure(1, weight=1)
        ttk.Label(options, text="Filters, one per line").grid(row=0, column=0, sticky="w")
        ttk.Label(options, text="Additional key=value parameters").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.cdx_filters_text = tk.Text(options, height=8, wrap="none", font="TkFixedFont")
        self.cdx_filters_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.cdx_extra_text = tk.Text(options, height=8, wrap="none", font="TkFixedFont")
        self.cdx_extra_text.grid(row=1, column=1, sticky="nsew", padx=(12, 0), pady=(4, 0))
        ttk.Button(tab, text="Preview CDX request", command=self.preview_cdx).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def create_media_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Media")
        options = ttk.Frame(tab)
        options.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(options, text="Also download media during a full text run", variable=self.media_enabled_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="Images", variable=self.media_images_var).grid(row=0, column=1, padx=(16, 0))
        ttk.Checkbutton(options, text="Videos", variable=self.media_videos_var).grid(row=0, column=2, padx=(8, 0))
        ttk.Checkbutton(options, text="Discover media linked inside saved pages", variable=self.media_embedded_var).grid(row=0, column=3, padx=(16, 0))
        ttk.Checkbutton(options, text="Allow external hosts", variable=self.media_external_var).grid(row=0, column=4, padx=(8, 0))
        labels = ttk.Frame(tab)
        labels.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        labels.columnconfigure(0, weight=1)
        labels.columnconfigure(1, weight=1)
        ttk.Label(labels, text="Media sites/paths (blank uses Sites and paths)").grid(row=0, column=0, sticky="w")
        ttk.Label(labels, text="Include extensions, one per line").grid(row=0, column=1, sticky="w", padx=(12, 0))
        editors = ttk.Frame(tab)
        editors.grid(row=2, column=0, columnspan=2, sticky="nsew")
        editors.columnconfigure(0, weight=1)
        editors.columnconfigure(1, weight=1)
        editors.columnconfigure(2, weight=1)
        editors.rowconfigure(0, weight=1)
        self.media_targets_text = tk.Text(editors, wrap="none", font="TkFixedFont")
        self.media_targets_text.grid(row=0, column=0, sticky="nsew")
        self.media_include_text = tk.Text(editors, wrap="none", font="TkFixedFont")
        self.media_include_text.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        right = ttk.Frame(editors)
        right.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="Exclude extensions, one per line").grid(row=0, column=0, sticky="w")
        self.media_exclude_text = tk.Text(right, wrap="none", font="TkFixedFont")
        self.media_exclude_text.grid(row=1, column=0, sticky="nsew")
        settings = ttk.Frame(tab)
        settings.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(settings, text="Snapshot:").grid(row=0, column=0)
        ttk.Combobox(settings, textvariable=self.media_strategy_var, values=("earliest", "latest", "all"), state="readonly", width=10).grid(row=0, column=1, padx=(5, 15))
        ttk.Label(settings, text="Maximum media size (MB):").grid(row=0, column=2)
        ttk.Entry(settings, textvariable=self.media_max_var, width=10).grid(row=0, column=3, padx=(5, 15))
        ttk.Checkbutton(settings, text="Preserve original path structure", variable=self.media_preserve_var).grid(row=0, column=4)

    def create_settings_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        tab.columnconfigure(1, weight=1)
        self.notebook.add(tab, text="Settings")
        rows = [
            ("Download workers", self.workers_var),
            ("Maximum text-page size (MB)", self.max_file_var),
            ("Minimum report score", self.minimum_score_var),
            ("CDX request delay (seconds)", self.cdx_delay_var),
            ("Download request delay (seconds)", self.download_delay_var),
        ]
        for row, (label, variable) in enumerate(rows):
            ttk.Label(tab, text=label + ":").grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(tab, textvariable=variable, width=18).grid(row=row, column=1, sticky="w", padx=(12, 0), pady=5)
        ttk.Label(tab, text="Download scope:").grid(row=len(rows), column=0, sticky="w", pady=5)
        ttk.Combobox(tab, textvariable=self.scope_var, values=list(SCOPE_LABELS), state="readonly", width=42).grid(row=len(rows), column=1, sticky="w", padx=(12, 0), pady=5)
        ttk.Label(tab, text="Worker count and request delays remain fixed for the entire run. Lower the worker count or increase the delays if the archive begins returning 429 or 5xx errors.", wraplength=760).grid(row=len(rows)+1, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def create_results_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Results and search")
        filters = ttk.Frame(tab)
        filters.grid(row=0, column=0, sticky="ew")
        filters.columnconfigure(1, weight=1)
        ttk.Label(filters, text="Scan:").grid(row=0, column=0)
        self.result_scan_box = ttk.Combobox(filters, textvariable=self.result_scan_var, state="readonly", width=38)
        self.result_scan_box.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(filters, text="Min score:").grid(row=0, column=2)
        ttk.Entry(filters, textvariable=self.result_min_var, width=7).grid(row=0, column=3, padx=5)
        ttk.Label(filters, text="Review:").grid(row=0, column=4)
        ttk.Combobox(filters, textvariable=self.result_review_filter_var, values=("All", *REVIEW_LABELS), state="readonly", width=18).grid(row=0, column=5, padx=5)
        ttk.Label(filters, text="Filter:").grid(row=0, column=6)
        ttk.Entry(filters, textvariable=self.result_filter_var, width=20).grid(row=0, column=7, padx=5)
        ttk.Button(filters, text="Refresh", command=self.refresh_results).grid(row=0, column=8)
        search = ttk.Frame(tab)
        search.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Instant full-text search:").grid(row=0, column=0)
        ttk.Entry(search, textvariable=self.fts_query_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Combobox(search, textvariable=self.fts_field_var, values=("all", "title", "body", "url"), state="readonly", width=8).grid(row=0, column=2, padx=5)
        ttk.Label(search, text="Domain:").grid(row=0, column=3)
        ttk.Entry(search, textvariable=self.fts_domain_var, width=18).grid(row=0, column=4, padx=5)
        ttk.Button(search, text="Search", command=self.run_fts_search).grid(row=0, column=5)
        pane = ttk.Panedwindow(tab, orient="vertical")
        pane.grid(row=2, column=0, sticky="nsew")
        top = ttk.Frame(pane)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        columns = ("score", "review", "timestamp", "title", "url", "hits")
        self.results_tree = ttk.Treeview(top, columns=columns, show="headings", selectmode="browse")
        widths = {"score": 70, "review": 120, "timestamp": 125, "title": 260, "url": 420, "hits": 100}
        for column in columns:
            self.results_tree.heading(column, text=column.title(), command=lambda name=column: self.sort_result_tree(name))
            self.results_tree.column(column, width=widths[column], anchor="w")
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        self.results_tree.bind("<<TreeviewSelect>>", self.load_selected_result)
        scroll = ttk.Scrollbar(top, orient="vertical", command=self.results_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.results_tree.configure(yscrollcommand=scroll.set)
        pane.add(top, weight=3)
        bottom = ttk.Frame(pane, padding=(0, 6, 0, 0))
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(1, weight=1)
        bottom.rowconfigure(2, weight=1)
        ttk.Label(bottom, text="Status:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(bottom, textvariable=self.review_status_var, values=list(REVIEW_LABELS), state="readonly", width=20).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(bottom, text="Tags:").grid(row=0, column=2)
        ttk.Entry(bottom, textvariable=self.review_tags_var, width=30).grid(row=0, column=3, padx=5)
        ttk.Button(bottom, text="Save review", command=self.save_selected_review).grid(row=0, column=4, padx=4)
        ttk.Button(bottom, text="Next unreviewed", command=self.select_next_unreviewed).grid(row=0, column=5, padx=2)
        ttk.Button(bottom, text="Open local", command=self.open_selected_local).grid(row=0, column=6, padx=2)
        ttk.Button(bottom, text="Open Wayback", command=self.open_selected_wayback).grid(row=0, column=7, padx=2)
        ttk.Button(bottom, text="Copy URL", command=self.copy_selected_url).grid(row=0, column=8, padx=2)
        ttk.Label(bottom, text="Notes:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.result_detail_text = tk.Text(bottom, height=4, wrap="word")
        self.result_detail_text.grid(row=1, column=1, columnspan=8, sticky="nsew", padx=(5, 0), pady=(6, 0))
        ttk.Label(bottom, text="Matching snippets:").grid(row=2, column=0, sticky="nw", pady=(6, 0))
        self.result_snippets_text = tk.Text(bottom, height=5, wrap="word", state="disabled")
        self.result_snippets_text.grid(row=2, column=1, columnspan=8, sticky="nsew", padx=(5, 0), pady=(6, 0))
        exports = ttk.Frame(bottom)
        exports.grid(row=3, column=1, columnspan=8, sticky="w", pady=(6, 0))
        ttk.Button(exports, text="Export CSV", command=lambda: self.export_results("csv")).grid(row=0, column=0, padx=2)
        ttk.Button(exports, text="Export JSON", command=lambda: self.export_results("json")).grid(row=0, column=1, padx=2)
        ttk.Button(exports, text="Export Markdown", command=lambda: self.export_results("markdown")).grid(row=0, column=2, padx=2)
        ttk.Button(exports, text="Review package", command=self.export_review_package_ui).grid(row=0, column=3, padx=2)
        pane.add(bottom, weight=1)

    def create_history_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.notebook.add(tab, text="Scan history")
        columns = ("id", "set", "status", "started", "documents", "matches", "seconds", "operation")
        self.history_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="extended")
        for column in columns:
            self.history_tree.heading(column, text=column.title())
            self.history_tree.column(column, width=110 if column not in {"set", "operation"} else 180)
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        buttons = ttk.Frame(tab)
        buttons.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh_history).grid(row=0, column=0, padx=2)
        ttk.Button(buttons, text="Rename", command=self.rename_selected_scan).grid(row=0, column=1, padx=2)
        ttk.Button(buttons, text="Regenerate reports", command=self.regenerate_selected_scan).grid(row=0, column=2, padx=2)
        ttk.Button(buttons, text="Delete scan results", command=self.delete_selected_scan).grid(row=0, column=3, padx=2)
        ttk.Button(buttons, text="Compare two scans", command=self.compare_selected_scans).grid(row=0, column=4, padx=2)

    def create_errors_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self.notebook.add(tab, text="Errors")
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(controls, text="Category:").grid(row=0, column=0)
        self.error_category_box = ttk.Combobox(controls, textvariable=self.error_category_var, state="readonly", values=("All",), width=24)
        self.error_category_box.grid(row=0, column=1, padx=5)
        ttk.Button(controls, text="Refresh", command=self.refresh_errors).grid(row=0, column=2, padx=2)
        ttk.Button(controls, text="Retry selected errors", command=self.retry_selected_errors).grid(row=0, column=3, padx=2)
        ttk.Button(controls, text="Ignore selected", command=self.ignore_selected_errors).grid(row=0, column=4, padx=2)
        columns = ("operation", "category", "attempts", "retryable", "last_seen", "url", "message")
        self.errors_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="extended")
        for column in columns:
            self.errors_tree.heading(column, text=column.title())
            self.errors_tree.column(column, width=110 if column not in {"url", "message"} else 300)
        self.errors_tree.grid(row=1, column=0, sticky="nsew")

    def create_activity_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.notebook.add(tab, text="Activity")
        self.log_text = tk.Text(tab, wrap="word", state="disabled", font="TkFixedFont")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def lines_from(self, widget: tk.Text) -> list[str]:
        return [line.strip() for line in widget.get("1.0", "end").splitlines() if line.strip()]

    def replace_text(self, widget: tk.Text, values: list[str]) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(values))

    def update_operation_help(self) -> None:
        self.operation_help_var.set(MODE_HELP.get(MODE_LABELS.get(self.mode_var.get(), "all"), ""))

    def save_current_keyword_set(self) -> None:
        if 0 <= self.current_keyword_set < len(self.keyword_sets):
            self.keyword_sets[self.current_keyword_set]["rules"] = self.lines_from(self.keywords_text)
            self.keyword_sets[self.current_keyword_set]["selected"] = self.keyword_set_selected_var.get()

    def refresh_keyword_set_box(self, selected_index: int | None = None) -> None:
        names = [item["name"] for item in self.keyword_sets]
        self.keyword_set_box.configure(values=names)
        if not names:
            self.current_keyword_set = -1
            self.keyword_set_var.set("")
            self.replace_text(self.keywords_text, [])
            return
        index = selected_index if selected_index is not None else min(max(self.current_keyword_set, 0), len(names)-1)
        self.current_keyword_set = index
        self.keyword_set_var.set(names[index])
        self.keyword_set_selected_var.set(bool(self.keyword_sets[index].get("selected", True)))
        self.replace_text(self.keywords_text, list(self.keyword_sets[index].get("rules") or []))

    def switch_keyword_set(self, _event=None) -> None:
        self.save_current_keyword_set()
        name = self.keyword_set_var.get()
        for index, item in enumerate(self.keyword_sets):
            if item["name"] == name:
                self.refresh_keyword_set_box(index)
                break

    def new_keyword_set(self) -> None:
        self.save_current_keyword_set()
        name = simpledialog.askstring(APP_NAME, "Name for the new keyword set:", initialvalue="New keyword set")
        if not name:
            return
        existing = {item["name"].casefold() for item in self.keyword_sets}
        base = name.strip()
        candidate = base
        suffix = 2
        while candidate.casefold() in existing:
            candidate = f"{base} {suffix}"
            suffix += 1
        self.keyword_sets.append({"name": candidate, "rules": [], "selected": True})
        self.refresh_keyword_set_box(len(self.keyword_sets)-1)

    def duplicate_keyword_set(self) -> None:
        self.save_current_keyword_set()
        if self.current_keyword_set < 0:
            return
        source = self.keyword_sets[self.current_keyword_set]
        self.keyword_sets.append({"name": source["name"] + " copy", "rules": list(source["rules"]), "selected": True})
        self.refresh_keyword_set_box(len(self.keyword_sets)-1)

    def delete_keyword_set(self) -> None:
        if self.current_keyword_set < 0:
            return
        if not messagebox.askyesno(APP_NAME, "Delete this keyword set from the project configuration?"):
            return
        del self.keyword_sets[self.current_keyword_set]
        self.refresh_keyword_set_box(max(0, self.current_keyword_set-1))

    def import_keyword_set(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text or JSON", "*.txt *.json"), ("All files", "*")])
        if not path:
            return
        p = Path(path)
        if p.suffix.casefold() == ".json":
            payload = json.loads(p.read_text(encoding="utf-8"))
            name = str(payload.get("name") or p.stem)
            rules = list(payload.get("rules") or payload.get("keywords") or [])
        else:
            name = p.stem
            rules = [line.strip() for line in p.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        self.keyword_sets.append({"name": name, "rules": rules, "selected": True})
        self.refresh_keyword_set_box(len(self.keyword_sets)-1)

    def export_keyword_set(self) -> None:
        self.save_current_keyword_set()
        if self.current_keyword_set < 0:
            return
        item = self.keyword_sets[self.current_keyword_set]
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=item["name"] + ".txt")
        if path:
            Path(path).write_text("\n".join(item["rules"]) + "\n", encoding="utf-8")

    def apply_preset(self) -> None:
        preset = PRESETS[self.preset_var.get()]
        self.replace_text(self.targets_text, list(preset["targets"]))
        self.keyword_sets = [{"name": "Current keywords", "rules": list(preset["keywords"]), "selected": True}]
        self.refresh_keyword_set_box(0)
        self.from_date_var.set(str(preset.get("from_date", preset["from_year"])))
        self.to_date_var.set(str(preset.get("to_date", preset["to_year"])))
        self.replace_text(self.cdx_filters_text, list(preset.get("cdx_filters", ["statuscode:200"])))
        self.replace_text(self.cdx_extra_text, list(preset.get("cdx_extra_params", [])))
        collapses = set(preset.get("cdx_collapses", ["urlkey"]))
        self.collapse_urlkey_var.set("urlkey" in collapses)
        self.collapse_digest_var.set("digest" in collapses)
        self.cdx_match_type_var.set(preset.get("cdx_match_type") or "Automatic")
        self.replace_text(self.media_include_text, list(DEFAULT_IMAGE_EXTENSIONS) + list(DEFAULT_VIDEO_EXTENSIONS))

    def build_config(self, require_keywords: bool = True) -> ProjectConfig:
        self.save_current_keyword_set()
        try:
            media = MediaConfig(
                enabled=self.media_enabled_var.get(),
                targets=self.lines_from(self.media_targets_text),
                include_images=self.media_images_var.get(),
                include_videos=self.media_videos_var.get(),
                include_extensions=self.lines_from(self.media_include_text),
                exclude_extensions=self.lines_from(self.media_exclude_text),
                discover_embedded=self.media_embedded_var.get(),
                allow_external_embeds=self.media_external_var.get(),
                snapshot_strategy=self.media_strategy_var.get(),
                max_file_mb=float(self.media_max_var.get()),
                preserve_paths=self.media_preserve_var.get(),
            )
            config = ProjectConfig(
                output_dir=Path(self.output_var.get()),
                targets=self.lines_from(self.targets_text),
                keywords=list(self.keyword_sets[0]["rules"]) if self.keyword_sets else [],
                keyword_set_name=self.keyword_sets[0]["name"] if self.keyword_sets else "Current keywords",
                keyword_sets=[KeywordSetConfig(item["name"], list(item["rules"]), bool(item.get("selected", True))) for item in self.keyword_sets],
                from_year=int(str(self.from_date_var.get()).strip()[:4]),
                to_year=int(str(self.to_date_var.get()).strip()[:4]),
                from_date=self.from_date_var.get(),
                to_date=self.to_date_var.get(),
                cdx_filters=self.lines_from(self.cdx_filters_text),
                cdx_collapses=[value for value, enabled in (("urlkey", self.collapse_urlkey_var.get()), ("digest", self.collapse_digest_var.get())) if enabled],
                cdx_match_type="" if self.cdx_match_type_var.get() == "Automatic" else self.cdx_match_type_var.get(),
                cdx_extra_params=self.lines_from(self.cdx_extra_text),
                page_size=int(self.page_size_var.get()),
                workers=int(self.workers_var.get()),
                download_scope=SCOPE_LABELS[self.scope_var.get()],
                minimum_score=int(self.minimum_score_var.get()),
                max_file_mb=float(self.max_file_var.get()),
                cdx_delay=float(self.cdx_delay_var.get()),
                download_delay=float(self.download_delay_var.get()),
                media=media,
            ).normalized()
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Check the numeric settings, keyword rules, and target lines: {exc}") from exc
        mode = MODE_LABELS[self.mode_var.get()]
        if mode in {"all", "index"} and not config.targets:
            raise ValueError("Add at least one site or path.")
        if require_keywords and mode in {"all", "download", "resume", "rescan", "retry_errors"} and not config.selected_keyword_sets():
            raise ValueError("Select at least one non-empty keyword set.")
        return config

    def preview_cdx(self) -> None:
        try:
            config = self.build_config(require_keywords=False)
            if not config.targets:
                raise ValueError("Add a target first.")
            window = cdx_year_window(config, config.from_year)
            if not window:
                raise ValueError("The selected date range does not contain an indexable year.")
            url = CDX_URL + "?" + urllib.parse.urlencode(build_cdx_params(config, config.targets[0], window[0], window[1]), doseq=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        dialog = tk.Toplevel(self)
        dialog.title("CDX request preview")
        dialog.geometry("860x420")
        text = tk.Text(dialog, wrap="word", font="TkFixedFont")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", url)
        text.configure(state="disabled")

    def choose_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.home()))
        if selected:
            self.output_var.set(selected)

    def open_output(self) -> None:
        open_path(Path(self.output_var.get()).expanduser())

    def open_reports(self) -> None:
        open_path(Path(self.output_var.get()).expanduser() / "reports")

    def start(self, override_config: ProjectConfig | None = None, override_mode: str | None = None) -> None:
        if self.worker_thread:
            if self.worker_thread.is_alive():
                self.status_var.set("The previous run is still shutting down…")
                self.log("Start ignored because the previous worker is still active.")
                messagebox.showinfo(APP_NAME, "The previous run is still active or shutting down. Wait for it to finish, then press Start again.")
                return
            self.worker_thread = None
        try:
            ensure_frozen_bundle_available()
            config = override_config or self.build_config()
        except (ValueError, FrozenBundleError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        mode = override_mode or MODE_LABELS[self.mode_var.get()]
        self.stop_event.clear()
        self.progress_var.set(0)
        self.status_var.set("Starting…")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.log(f"Starting {mode} in {config.output_dir}")
        self.worker_thread = threading.Thread(target=self.run_worker, args=(config, mode), daemon=True)
        self.worker_thread.start()

    def run_worker(self, config: ProjectConfig, mode: str) -> None:
        try:
            self.events.put(("complete", run_project(config, mode, self.stop_event, self.on_engine_event)))
        except Stopped:
            self.events.put(("stopped", None))
        except FrozenBundleError as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            self.events.put(("error", traceback.format_exc()))

    def on_engine_event(self, event: ProgressEvent) -> None:
        self.events.put(("progress", event))

    def stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping after the current request…")
        self.stop_button.configure(state="disabled")

    def process_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    event = payload
                    self.status_var.set(event.message)
                    self.log(event.message)
                    if event.current is not None and event.total:
                        self.progress.configure(mode="determinate")
                        self.progress_var.set(event.current / event.total * 100)
                    else:
                        self.progress.configure(mode="indeterminate")
                        self.progress.start(12)
                elif kind == "complete":
                    self.last_paths = payload
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress_var.set(100)
                    self.status_var.set("Complete")
                    self.log("Complete. Reports are ready.")
                    self.finish_run()
                    self.refresh_history()
                    self.refresh_results()
                    self.refresh_errors()
                    messagebox.showinfo(APP_NAME, "The run is complete.")
                elif kind == "stopped":
                    self.progress.stop()
                    self.status_var.set("Stopped. Progress was saved.")
                    self.finish_run()
                elif kind == "error":
                    self.progress.stop()
                    self.status_var.set("Error")
                    self.log(str(payload))
                    self.finish_run()
                    messagebox.showerror(APP_NAME, str(payload))
        except queue.Empty:
            pass
        self.after(100, self.process_events)

    def finish_run(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.after(50, self.finish_run)
            return
        self.worker_thread = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.save_app_state()

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def project_database(self):
        return open_database(Path(self.output_var.get()).expanduser(), migrate=True)

    def refresh_scan_choices(self, database=None) -> None:
        own = database is None
        database = database or self.project_database()
        try:
            runs = list_scan_runs(database)
            self.scan_run_map = {f"{row['id']} — {row['keyword_set_name']} — {row['status']}": int(row["id"]) for row in runs}
            values = list(self.scan_run_map)
            self.result_scan_box.configure(values=values)
            if values and self.result_scan_var.get() not in self.scan_run_map:
                self.result_scan_var.set(values[0])
        finally:
            if own:
                database.close()

    def refresh_results(self) -> None:
        root = Path(self.output_var.get()).expanduser()
        if not (root / "archive_scout.sqlite3").exists():
            return
        database = self.project_database()
        try:
            self.refresh_scan_choices(database)
            scan_id = self.scan_run_map.get(self.result_scan_var.get())
            if scan_id is None:
                return
            status = REVIEW_LABELS.get(self.result_review_filter_var.get(), "") if self.result_review_filter_var.get() != "All" else ""
            rows = result_rows(database, scan_id, int(self.result_min_var.get() or 0), status, self.result_filter_var.get())
            self.results_tree.delete(*self.results_tree.get_children())
            self.result_row_map.clear()
            for row in rows:
                item = self.results_tree.insert("", "end", values=(row["score"], row["review_status"], row["timestamp"], row["title"] or "(untitled)", row["original_url"], len(json.loads(row["hits_json"] or "{}"))))
                self.result_row_map[item] = dict(row)
        except Exception as exc:
            self.log(f"Could not load results: {exc}")
        finally:
            database.close()

    def run_fts_search(self) -> None:
        database = self.project_database()
        try:
            rows = search_documents(
                database,
                self.fts_query_var.get(),
                field=self.fts_field_var.get(),
                domain=self.fts_domain_var.get(),
                scan_run_id=self.current_scan_id(),
            )
            self.results_tree.delete(*self.results_tree.get_children())
            self.result_row_map.clear()
            for row in rows:
                data = dict(row)
                data.update({"id": 0, "score": round(-float(row["rank"]), 3), "review_status": "search", "hits_json": "{}", "snippets_json": json.dumps([row["snippet"] or ""]), "note": "", "tags": ""})
                item = self.results_tree.insert("", "end", values=(data["score"], "search", row["timestamp"], row["title"] or "(untitled)", row["original_url"], "FTS"))
                self.result_row_map[item] = data
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
        finally:
            database.close()

    def sort_result_tree(self, column: str) -> None:
        if self.result_sort_column == column:
            self.result_sort_reverse = not self.result_sort_reverse
        else:
            self.result_sort_column = column
            self.result_sort_reverse = column in {"score", "timestamp", "hits"}
        items = list(self.results_tree.get_children())
        def key(item: str):
            value = self.results_tree.set(item, column)
            if column in {"score", "hits"}:
                try:
                    return float(value)
                except ValueError:
                    return float("-inf")
            return value.casefold()
        items.sort(key=key, reverse=self.result_sort_reverse)
        for index, item in enumerate(items):
            self.results_tree.move(item, "", index)

    def select_next_unreviewed(self) -> None:
        items = list(self.results_tree.get_children())
        if not items:
            return
        selected = self.results_tree.selection()
        start = items.index(selected[0]) + 1 if selected and selected[0] in items else 0
        for offset in range(len(items)):
            item = items[(start + offset) % len(items)]
            row = self.result_row_map.get(item, {})
            if row.get("review_status", "unreviewed") == "unreviewed":
                self.results_tree.selection_set(item)
                self.results_tree.focus(item)
                self.results_tree.see(item)
                self.load_selected_result()
                return
        messagebox.showinfo(APP_NAME, "There are no unreviewed results in the current view.")

    def selected_result(self) -> dict | None:
        selected = self.results_tree.selection()
        return self.result_row_map.get(selected[0]) if selected else None

    def load_selected_result(self, _event=None) -> None:
        row = self.selected_result()
        if not row:
            return
        reverse = {value: label for label, value in REVIEW_LABELS.items()}
        self.review_status_var.set(reverse.get(row.get("review_status"), "Unreviewed"))
        self.review_tags_var.set(row.get("tags") or "")
        snippets = json.loads(row.get("snippets_json") or "[]")
        detail = (row.get("note") or "") + ("\n\n" if row.get("note") and snippets else "") + "\n\n".join(snippets)
        self.result_detail_text.delete("1.0", "end")
        self.result_detail_text.insert("1.0", detail)

    def save_selected_review(self) -> None:
        row = self.selected_result()
        if not row or not row.get("id"):
            return
        database = self.project_database()
        try:
            with database:
                set_review(database, int(row["id"]), REVIEW_LABELS[self.review_status_var.get()])
                save_note(database, int(row["id"]), self.result_detail_text.get("1.0", "end").strip())
                set_match_tags(database, int(row["id"]), [value.strip() for value in self.review_tags_var.get().split(",")])
            self.refresh_results()
        finally:
            database.close()

    def open_selected_local(self) -> None:
        row = self.selected_result()
        if row and row.get("path"):
            path = Path(row["path"])
            if path.exists():
                if sys.platform == "darwin": subprocess.Popen(["open", str(path)])
                elif os.name == "nt": os.startfile(str(path))
                else: subprocess.Popen(["xdg-open", str(path)])

    def open_selected_wayback(self) -> None:
        row = self.selected_result()
        if row:
            webbrowser.open(replay_url(row["timestamp"], row["original_url"]))

    def copy_selected_url(self) -> None:
        row = self.selected_result()
        if row:
            self.clipboard_clear()
            self.clipboard_append(row["original_url"])

    def current_scan_id(self) -> int | None:
        return self.scan_run_map.get(self.result_scan_var.get())

    def export_results(self, format_name: str) -> None:
        scan_id = self.current_scan_id()
        if not scan_id:
            return
        extension = ".md" if format_name == "markdown" else "." + format_name
        path = filedialog.asksaveasfilename(defaultextension=extension, initialfile=f"scan-{scan_id}{extension}")
        if not path:
            return
        database = self.project_database()
        try:
            status = REVIEW_LABELS.get(self.result_review_filter_var.get(), "") if self.result_review_filter_var.get() != "All" else ""
            export_scan(
                database, scan_id, Path(path), format_name, status,
                int(self.result_min_var.get() or 0), self.result_filter_var.get(),
            )
        finally:
            database.close()

    def export_review_package_ui(self) -> None:
        scan_id = self.current_scan_id()
        if not scan_id:
            return
        path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=f"scan-{scan_id}-review.zip")
        if not path:
            return
        database = self.project_database()
        try:
            status = REVIEW_LABELS.get(self.result_review_filter_var.get(), "") if self.result_review_filter_var.get() != "All" else ""
            export_review_package(
                database, scan_id, Path(path), status,
                int(self.result_min_var.get() or 0), self.result_filter_var.get(),
            )
        finally:
            database.close()

    def refresh_history(self) -> None:
        root = Path(self.output_var.get()).expanduser()
        if not (root / "archive_scout.sqlite3").exists():
            return
        database = self.project_database()
        try:
            self.history_tree.delete(*self.history_tree.get_children())
            for row in list_scan_runs(database):
                self.history_tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["keyword_set_name"], row["status"], row["started_at"], row["document_count"], row["match_count"], f"{row['duration_seconds']:.1f}", row["source_operation"]))
            self.refresh_scan_choices(database)
        finally:
            database.close()

    def selected_history_id(self) -> int | None:
        selected = self.history_tree.selection()
        return int(selected[0]) if selected else None

    def compare_selected_scans(self) -> None:
        selected = [int(value) for value in self.history_tree.selection()]
        if len(selected) != 2:
            messagebox.showinfo(APP_NAME, "Select exactly two scan runs to compare.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"scan-{selected[0]}-vs-{selected[1]}.txt",
        )
        if not path:
            return
        database = self.project_database()
        try:
            generate_scan_comparison(database, selected[0], selected[1], Path(path))
        finally:
            database.close()

    def rename_selected_scan(self) -> None:
        scan_id = self.selected_history_id()
        if not scan_id:
            return
        name = simpledialog.askstring(APP_NAME, "New scan name:")
        if name:
            database = self.project_database()
            with database:
                rename_scan_run(database, scan_id, name)
            database.close()
            self.refresh_history()

    def regenerate_selected_scan(self) -> None:
        scan_id = self.selected_history_id()
        if not scan_id:
            return
        database = self.project_database()
        try:
            generate_reports(self.build_config(require_keywords=False), database, scan_id)
        finally:
            database.close()

    def delete_selected_scan(self) -> None:
        scan_id = self.selected_history_id()
        if not scan_id or not messagebox.askyesno(APP_NAME, "Delete this scan's matches, reviews, notes, and tags? Downloaded files will remain."):
            return
        database = self.project_database()
        with database:
            delete_scan_run(database, scan_id)
        database.close()
        self.refresh_history()

    def refresh_errors(self) -> None:
        root = Path(self.output_var.get()).expanduser()
        if not (root / "archive_scout.sqlite3").exists():
            return
        database = self.project_database()
        try:
            rows = list_errors(database)
            categories = sorted({row["category"] for row in rows})
            self.error_category_box.configure(values=("All", *categories))
            selected_category = self.error_category_var.get()
            self.errors_tree.delete(*self.errors_tree.get_children())
            self.error_row_map.clear()
            for row in rows:
                if selected_category != "All" and row["category"] != selected_category:
                    continue
                url = row["original_url"] or row["media_url"] or row["path"] or row["media_path"] or ""
                item = self.errors_tree.insert("", "end", values=(row["operation"], row["category"], row["attempt_count"], bool(row["retryable"]), row["last_seen"], url, row["message"]))
                self.error_row_map[item] = dict(row)
        finally:
            database.close()

    def retry_selected_errors(self) -> None:
        selected = [self.error_row_map[item] for item in self.errors_tree.selection() if item in self.error_row_map]
        capture_ids = sorted({int(row["capture_id"]) for row in selected if row.get("capture_id")})
        media_ids = sorted({int(row["media_capture_id"]) for row in selected if row.get("media_capture_id")})
        if not capture_ids and not media_ids:
            messagebox.showinfo(APP_NAME, "Select one or more retryable text-page or media errors.")
            return
        config = self.build_config(require_keywords=bool(capture_ids))
        config.retry_capture_ids = capture_ids
        config.retry_media_capture_ids = media_ids
        if capture_ids:
            self.start(config.normalized(), "retry_errors")
        else:
            self.start(config.normalized(), "media_retry")

    def ignore_selected_errors(self) -> None:
        ids = [int(self.error_row_map[item]["id"]) for item in self.errors_tree.selection() if item in self.error_row_map]
        if not ids:
            return
        database = self.project_database()
        with database:
            ignore_errors(database, ids, True)
        database.close()
        self.refresh_errors()

    def save_project(self) -> None:
        try:
            path = save_project_config(self.build_config(require_keywords=False))
            messagebox.showinfo(APP_NAME, f"Project saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def load_project(self) -> None:
        selected = filedialog.askopenfilename(title="Load Archive Scout project", filetypes=[("Archive Scout project", "project.json"), ("JSON files", "*.json"), ("All files", "*")])
        if not selected:
            return
        try:
            self.apply_config(load_project_config(Path(selected)))
            self.refresh_history()
            self.refresh_results()
            self.refresh_errors()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not load project:\n{exc}")

    def apply_config(self, config: ProjectConfig) -> None:
        self.output_var.set(str(config.output_dir))
        self.replace_text(self.targets_text, config.targets)
        self.keyword_sets = [item.to_payload() for item in config.normalized_keyword_sets()]
        self.refresh_keyword_set_box(0)
        self.from_date_var.set(config.from_date)
        self.to_date_var.set(config.to_date)
        self.replace_text(self.cdx_filters_text, config.cdx_filters)
        self.replace_text(self.cdx_extra_text, config.cdx_extra_params)
        self.collapse_urlkey_var.set("urlkey" in config.cdx_collapses)
        self.collapse_digest_var.set("digest" in config.cdx_collapses)
        self.cdx_match_type_var.set(config.cdx_match_type or "Automatic")
        self.page_size_var.set(str(config.page_size))
        self.workers_var.set(str(config.workers))
        self.max_file_var.set(str(config.max_file_mb))
        self.minimum_score_var.set(str(config.minimum_score))
        self.cdx_delay_var.set(str(config.cdx_delay))
        self.download_delay_var.set(str(config.download_delay))
        for label, value in SCOPE_LABELS.items():
            if value == config.download_scope:
                self.scope_var.set(label)
                break
        media = config.media
        self.media_enabled_var.set(media.enabled)
        self.replace_text(self.media_targets_text, media.targets)
        self.media_images_var.set(media.include_images)
        self.media_videos_var.set(media.include_videos)
        self.replace_text(self.media_include_text, media.include_extensions)
        self.replace_text(self.media_exclude_text, media.exclude_extensions)
        self.media_embedded_var.set(media.discover_embedded)
        self.media_external_var.set(media.allow_external_embeds)
        self.media_strategy_var.set(media.snapshot_strategy)
        self.media_max_var.set(str(media.max_file_mb))
        self.media_preserve_var.set(media.preserve_paths)

    def state_path(self) -> Path:
        return app_support_dir() / "settings.json"

    def save_app_state(self) -> None:
        try:
            config = self.build_config(require_keywords=False)
            path = self.state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = config.to_payload()
            payload["mode"] = self.mode_var.get()
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass

    def load_app_state(self) -> None:
        path = self.state_path()
        if not path.exists():
            return
        try:
            config = load_project_config(path)
            self.apply_config(config)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("mode") in MODE_LABELS:
                self.mode_var.set(payload["mode"])
            self.update_operation_help()
        except Exception:
            pass

    def on_close(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            if not messagebox.askyesno(APP_NAME, "A run is active. Stop it and close the application?"):
                return
            self.stop_event.set()
        self.save_app_state()
        self.destroy()


def main() -> None:
    app = ArchiveScoutApp()
    app.mainloop()


if __name__ == "__main__":
    main()
