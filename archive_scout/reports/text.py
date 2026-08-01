from __future__ import annotations

import json
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

from ..config import ProjectConfig
from ..downloads.downloader import replay_url
from ..utils import atomic_write_text, json_value, utc_now

REPORT_NAMES = (
    "matches_ranked.txt",
    "matched_urls.txt",
    "wayback_urls.txt",
    "interesting_links.txt",
    "keyword_counts.txt",
    "all_indexed_urls.txt",
    "errors.txt",
    "summary.txt",
)


def safe_run_name(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in value.strip())
    return cleaned.strip("-")[:60] or "scan"


def generate_reports(
    config: ProjectConfig,
    database: sqlite3.Connection,
    scan_run_id: int,
) -> dict[str, Path]:
    run = database.execute(
        """
        SELECT sr.*,ks.name AS keyword_set_name,ks.keywords_json
        FROM scan_runs sr JOIN keyword_sets ks ON ks.id=sr.keyword_set_id WHERE sr.id=?
        """,
        (scan_run_id,),
    ).fetchone()
    if not run:
        raise RuntimeError(f"scan run {scan_run_id} does not exist")
    run_dir = config.output_dir / "reports" / f"scan-{scan_run_id:05d}-{safe_run_name(run['keyword_set_name'])}"
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = database.execute(
        """
        SELECT m.*,d.path,d.title,d.size_bytes,c.original_url,c.timestamp,c.mimetype,c.state,
               COALESCE(r.status,'unreviewed') AS review_status,
               COALESCE((SELECT text FROM notes n WHERE n.match_id=m.id ORDER BY n.id LIMIT 1),'') AS note,
               COALESCE((SELECT GROUP_CONCAT(t.name, ', ') FROM match_tags mt JOIN tags t ON t.id=mt.tag_id WHERE mt.match_id=m.id),'') AS tags
        FROM document_matches m
        JOIN documents d ON d.id=m.document_id
        JOIN captures c ON c.id=d.capture_id
        LEFT JOIN reviews r ON r.match_id=m.id
        WHERE m.scan_run_id=? AND m.score>=? AND m.excluded=0 AND m.required_missing=0
        ORDER BY m.score DESC,c.timestamp,c.original_url
        """,
        (scan_run_id, config.minimum_score),
    ).fetchall()
    all_rows = database.execute(
        "SELECT timestamp,mimetype,state,original_url,query_signature FROM captures ORDER BY original_url,timestamp"
    ).fetchall()
    state_counts = dict(database.execute("SELECT state,COUNT(*) FROM captures GROUP BY state").fetchall())
    keyword_counts: Counter[str] = Counter()
    ranked_blocks: list[str] = []
    matched_urls: list[str] = []
    wayback_urls: list[str] = []
    link_rows: list[tuple[str, str]] = []
    for rank, row in enumerate(rows, 1):
        hits = json_value(row["hits_json"], {})
        fields = json_value(row["fields_json"], {})
        snippets = json_value(row["snippets_json"], [])
        links = json_value(row["interesting_links_json"], [])
        keyword_counts.update(hits)
        matched_urls.append(row["original_url"])
        wayback_urls.append(replay_url(row["timestamp"], row["original_url"]))
        hit_lines = [
            f"{label}={count} [{','.join(fields.get(label, []))}]"
            for label, count in sorted(hits.items(), key=lambda item: (-item[1], item[0].casefold()))
        ]
        snippet_lines = [f"  {index}. {snippet}" for index, snippet in enumerate(snippets, 1)] or ["  None"]
        link_lines = [f"  {link}" for link in links] or ["  None"]
        link_rows.extend((row["original_url"], link) for link in links)
        ranked_blocks.append(
            "\n".join(
                [
                    "=" * 100,
                    f"RANK: {rank}",
                    f"SCORE: {row['score']}",
                    f"SCAN RUN: {scan_run_id}",
                    f"TIMESTAMP: {row['timestamp']}",
                    f"TITLE: {row['title'] or '(untitled)'}",
                    f"ORIGINAL URL: {row['original_url']}",
                    f"WAYBACK URL: {replay_url(row['timestamp'], row['original_url'])}",
                    f"LOCAL FILE: {row['path']}",
                    f"MIME TYPE: {row['mimetype'] or '(unknown)'}",
                    f"REVIEW STATUS: {row['review_status']}",
                    f"TAGS: {row['tags'] or '(none)'}",
                    f"NOTE: {row['note'] or '(none)'}",
                    f"KEYWORD HITS: {'; '.join(hit_lines) if hit_lines else 'None'}",
                    "SNIPPETS:",
                    *snippet_lines,
                    "INTERESTING LINKS:",
                    *link_lines,
                ]
            )
        )
    unresolved_errors = database.execute(
        """
        SELECT e.*,c.timestamp,c.original_url,d.path
        FROM errors e
        LEFT JOIN captures c ON c.id=e.capture_id
        LEFT JOIN documents d ON d.id=e.document_id
        WHERE e.resolved=0
        ORDER BY e.operation,e.category,e.last_seen,e.id
        """
    ).fetchall()
    error_lines = [
        "\t".join(
            [
                row["last_seen"],
                f"operation={row['operation']}",
                f"category={row['category']}",
                f"attempts={row['attempt_count']}",
                f"retryable={bool(row['retryable'])}",
                f"status={row['http_status'] or ''}",
                row["timestamp"] or "",
                row["original_url"] or row["path"] or "",
                row["message"],
            ]
        )
        for row in unresolved_errors
    ]
    keywords = json.loads(run["keywords_json"])
    summary_lines = [
        "Archive Scout 2.0",
        f"Generated: {utc_now()}",
        f"Output directory: {config.output_dir}",
        f"Scan run: {scan_run_id}",
        f"Keyword set: {run['keyword_set_name']}",
        f"Keyword rules: {len(keywords):,}",
        f"Scan source operation: {run['source_operation']}",
        f"Scan started: {run['started_at']}",
        f"Scan completed: {run['completed_at'] or '(not marked complete)'}",
        f"Targets: {', '.join(config.targets) or '(project database only)'}",
        f"Date range: {config.from_date}-{config.to_date}",
        f"Indexed captures: {len(all_rows):,}",
        f"Ranked matches at score >= {config.minimum_score}: {len(rows):,}",
        f"Unresolved errors: {len(unresolved_errors):,}",
        "States: " + ", ".join(f"{key}={value:,}" for key, value in sorted(state_counts.items())),
    ]
    contents = {
        "matches_ranked.txt": "\n\n".join(ranked_blocks) + ("\n" if ranked_blocks else ""),
        "matched_urls.txt": "\n".join(dict.fromkeys(matched_urls)) + ("\n" if matched_urls else ""),
        "wayback_urls.txt": "\n".join(dict.fromkeys(wayback_urls)) + ("\n" if wayback_urls else ""),
        "interesting_links.txt": "\n".join(f"{source}\t{link}" for source, link in sorted(set(link_rows))) + ("\n" if link_rows else ""),
        "keyword_counts.txt": "\n".join(f"{count}\t{label}" for label, count in keyword_counts.most_common()) + ("\n" if keyword_counts else ""),
        "all_indexed_urls.txt": "\n".join(
            f"{row['timestamp']}\t{row['mimetype'] or ''}\t{row['state']}\t{row['original_url']}" for row in all_rows
        ) + ("\n" if all_rows else ""),
        "errors.txt": "\n".join(error_lines) + ("\n" if error_lines else ""),
        "summary.txt": "\n".join(summary_lines) + "\n",
    }
    paths: dict[str, Path] = {}
    root_reports = config.output_dir / "reports"
    for name, text in contents.items():
        run_path = run_dir / name
        latest_path = root_reports / name
        atomic_write_text(run_path, text)
        atomic_write_text(latest_path, text)
        paths[name.removesuffix(".txt")] = latest_path
    atomic_write_text(root_reports / "latest_scan_run.txt", f"{scan_run_id}\n{run_dir}\n")
    paths["scan_folder"] = run_dir
    return paths
