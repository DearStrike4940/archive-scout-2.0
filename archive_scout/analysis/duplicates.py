from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from ..utils import normalize_search, utc_now

TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)


@dataclass(slots=True)
class DuplicateSummary:
    exact_groups: int = 0
    near_groups: int = 0
    grouped_documents: int = 0


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(normalize_search(text))


def simhash64(text: str) -> int:
    tokens = _tokens(text)
    if not tokens:
        return 0
    features: list[str] = []
    if len(tokens) < 4:
        features = tokens
    else:
        features = [" ".join(tokens[index:index + 4]) for index in range(len(tokens) - 3)]
    vector = [0] * 64
    counts: dict[str, int] = defaultdict(int)
    for feature in features:
        counts[feature] += 1
    for feature, weight in counts.items():
        digest = hashlib.blake2b(feature.encode("utf-8", "replace"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        scaled = 1 + int(math.log2(weight))
        for bit in range(64):
            vector[bit] += scaled if value & (1 << bit) else -scaled
    result = 0
    for bit, score in enumerate(vector):
        if score >= 0:
            result |= 1 << bit
    return result


def hamming_similarity(left: int, right: int) -> float:
    return 1.0 - ((left ^ right).bit_count() / 64.0)


class _UnionFind:
    def __init__(self, values: list[int]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: int) -> int:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            next_value = self.parent[value]
            self.parent[value] = root
            value = next_value
        return root

    def union(self, left: int, right: int) -> None:
        a = self.find(left)
        b = self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def cluster_duplicates(database: sqlite3.Connection, threshold: float = 0.90) -> DuplicateSummary:
    threshold = min(1.0, max(0.5, float(threshold)))
    rows = database.execute(
        """
        SELECT d.id,d.body_text,d.content_hash,d.normalized_hash,c.timestamp,c.original_url
        FROM documents d JOIN captures c ON c.id=d.capture_id
        WHERE COALESCE(d.body_text,'')<>''
        ORDER BY d.id
        """
    ).fetchall()
    document_ids = [int(row["id"]) for row in rows]
    union = _UnionFind(document_ids)
    method_for_pair: dict[tuple[int, int], tuple[str, float]] = {}

    exact: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        key = str(row["normalized_hash"] or row["content_hash"] or "")
        if key:
            exact[key].append(int(row["id"]))
    for ids in exact.values():
        if len(ids) < 2:
            continue
        first = ids[0]
        for other in ids[1:]:
            union.union(first, other)
            method_for_pair[(min(first, other), max(first, other))] = ("exact", 1.0)

    hashes: dict[int, int] = {}
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row in rows:
        document_id = int(row["id"])
        value = simhash64(str(row["body_text"] or ""))
        hashes[document_id] = value
        for band in range(4):
            buckets[(band, (value >> (band * 16)) & 0xFFFF)].append(document_id)

    compared: set[tuple[int, int]] = set()
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        # Avoid pathological buckets created by empty or boilerplate-only pages.
        if len(ids) > 2000:
            ids = ids[:2000]
        for index, left in enumerate(ids):
            for right in ids[index + 1:]:
                pair = (min(left, right), max(left, right))
                if pair in compared:
                    continue
                compared.add(pair)
                similarity = hamming_similarity(hashes[left], hashes[right])
                if similarity >= threshold:
                    union.union(left, right)
                    method_for_pair.setdefault(pair, ("near", similarity))

    grouped: dict[int, list[int]] = defaultdict(list)
    for document_id in document_ids:
        grouped[union.find(document_id)].append(document_id)
    groups = [sorted(ids) for ids in grouped.values() if len(ids) > 1]

    with database:
        database.execute("DELETE FROM duplicate_members")
        database.execute("DELETE FROM duplicate_groups")
        summary = DuplicateSummary()
        for ids in sorted(groups, key=lambda item: (item[0], len(item))):
            representative = ids[0]
            all_exact = True
            similarities: dict[int, float] = {representative: 1.0}
            for document_id in ids[1:]:
                pair = (min(representative, document_id), max(representative, document_id))
                method, similarity = method_for_pair.get(pair, ("near", hamming_similarity(hashes[representative], hashes[document_id])))
                if method != "exact":
                    all_exact = False
                similarities[document_id] = similarity
            method = "exact" if all_exact else "near"
            cursor = database.execute(
                "INSERT INTO duplicate_groups(method,representative_document_id,created_at) VALUES(?,?,?)",
                (method, representative, utc_now()),
            )
            group_id = int(cursor.lastrowid)
            for document_id in ids:
                database.execute(
                    "INSERT INTO duplicate_members(group_id,document_id,similarity) VALUES(?,?,?)",
                    (group_id, document_id, similarities.get(document_id, 1.0)),
                )
            if method == "exact":
                summary.exact_groups += 1
            else:
                summary.near_groups += 1
            summary.grouped_documents += len(ids)
    return summary
