"""Deterministic weighted Unicode n-gram BM25 routing for frozen tool cards."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from typing import Any, Iterable


HAN_SEGMENT = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
LATIN_TOKEN = re.compile(r"[a-z]+[a-z0-9]*")
NUMERIC_TOKEN = re.compile(r"\d+(?:\.\d+)?")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_text(text: Any, tokenizer: dict[str, Any]) -> str:
    normalized = unicodedata.normalize(
        tokenizer["unicode_normalization"], str(text or "")
    )
    if tokenizer["casefold"]:
        normalized = normalized.casefold()
    return normalized.replace("_", " ").replace("-", " ")


def tokenize(text: Any, tokenizer: dict[str, Any]) -> list[str]:
    normalized = normalize_text(text, tokenizer)
    tokens: list[str] = []
    for segment in HAN_SEGMENT.findall(normalized):
        for size in tokenizer["chinese_character_ngram_sizes"]:
            if len(segment) < size:
                continue
            tokens.extend(
                f"zh{size}:{segment[index:index + size]}"
                for index in range(len(segment) - size + 1)
            )
    if tokenizer["latin_alphanumeric_tokens"]:
        tokens.extend(f"lat:{value}" for value in LATIN_TOKEN.findall(normalized))
    if tokenizer["numeric_tokens"]:
        tokens.extend(f"num:{value}" for value in NUMERIC_TOKEN.findall(normalized))
    return tokens


def _parameter_texts(parameters: dict[str, Any]) -> tuple[list[str], list[str]]:
    names: list[str] = []
    descriptions: list[str] = []

    def visit(schema: Any) -> None:
        if not isinstance(schema, dict):
            return
        for name, child in schema.get("properties", {}).items():
            names.append(str(name))
            if isinstance(child, dict):
                if child.get("description"):
                    descriptions.append(str(child["description"]))
                visit(child)
        items = schema.get("items")
        if isinstance(items, dict):
            visit(items)
        for key in ("anyOf", "oneOf", "allOf"):
            for branch in schema.get(key, []):
                visit(branch)

    visit(parameters)
    return names, descriptions


def tool_fields(entry: dict[str, Any]) -> dict[str, list[str]]:
    function = entry["openai_tool"]["function"]
    parameter_names, parameter_descriptions = _parameter_texts(
        function.get("parameters", {})
    )
    return {
        "tool_name": [entry.get("tool_name", "")],
        "semantic_alias": [entry.get("semantic_alias", "")],
        "scenario": [entry.get("scenario", "")],
        "tool_type": [entry.get("tool_type", "")],
        "core_method": [entry.get("core_method", "")],
        "main_input": [entry.get("main_input", "")],
        "main_output": [entry.get("main_output", "")],
        "applicable_boundary_risk": [entry.get("applicable_boundary_risk", "")],
        "function_description": [function.get("description", "")],
        "parameter_name": parameter_names,
        "parameter_description": parameter_descriptions,
    }


class WeightedUnicodeNgramBM25:
    """A dependency-free, hashable lexical retriever over a frozen registry."""

    def __init__(self, entries: Iterable[dict[str, Any]], config: dict[str, Any]):
        self.config = deepcopy(config)
        entry_rows = list(entries)
        self.entries = {entry["tool_id"]: deepcopy(entry) for entry in entry_rows}
        if not self.entries:
            raise ValueError("lexical index requires at least one tool")
        if len(self.entries) != len(entry_rows):
            raise ValueError("tool registry contains duplicate IDs")
        self.document_terms: dict[str, Counter[str]] = {}
        self.document_lengths: dict[str, float] = {}
        document_frequency: Counter[str] = Counter()
        for tool_id, entry in sorted(self.entries.items()):
            terms: Counter[str] = Counter()
            for field, values in tool_fields(entry).items():
                boost = int(config["field_boosts"][field])
                if boost < 1:
                    raise ValueError(f"field boost must be positive: {field}")
                for value in values:
                    for token in tokenize(value, config["tokenizer"]):
                        terms[token] += boost
            self.document_terms[tool_id] = terms
            self.document_lengths[tool_id] = float(sum(terms.values()))
            document_frequency.update(terms.keys())
        self.document_frequency = dict(document_frequency)
        self.document_count = len(self.entries)
        self.average_document_length = (
            sum(self.document_lengths.values()) / self.document_count
        )
        if self.average_document_length <= 0:
            raise ValueError("lexical index contains no tokens")
        self.index_sha256 = json_hash(
            {
                "algorithm": config["algorithm"],
                "bm25": config["bm25"],
                "tokenizer": config["tokenizer"],
                "field_boosts": config["field_boosts"],
                "documents": {
                    tool_id: dict(sorted(terms.items()))
                    for tool_id, terms in sorted(self.document_terms.items())
                },
            }
        )

    def _idf(self, token: str) -> float:
        df = self.document_frequency.get(token, 0)
        return math.log(1.0 + (self.document_count - df + 0.5) / (df + 0.5))

    def _score(self, query_terms: Counter[str], tool_id: str) -> tuple[float, list[dict[str, Any]]]:
        terms = self.document_terms[tool_id]
        length = self.document_lengths[tool_id]
        k1 = float(self.config["bm25"]["k1"])
        b = float(self.config["bm25"]["b"])
        contributions = []
        total = 0.0
        for token, query_frequency in query_terms.items():
            tf = float(terms.get(token, 0))
            if tf <= 0:
                continue
            denominator = tf + k1 * (
                1.0 - b + b * length / self.average_document_length
            )
            value = self._idf(token) * (tf * (k1 + 1.0) / denominator)
            value *= 1.0 + math.log(float(query_frequency))
            total += value
            contributions.append(
                {
                    "token": token,
                    "weighted_document_tf": int(tf),
                    "contribution": round(value, 8),
                }
            )
        contributions.sort(key=lambda row: (-row["contribution"], row["token"]))
        return round(total, 8), contributions

    def retrieve(self, query: str, pool_tool_ids: list[str], *, top_k: int = 5) -> dict[str, Any]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if len(pool_tool_ids) != len(set(pool_tool_ids)):
            raise ValueError("candidate pool contains duplicate tool IDs")
        missing = [tool_id for tool_id in pool_tool_ids if tool_id not in self.entries]
        if missing:
            raise ValueError(f"candidate pool contains unindexed tools: {missing}")
        query_terms = Counter(tokenize(query, self.config["tokenizer"]))
        ranked = []
        for tool_id in pool_tool_ids:
            score, contributions = self._score(query_terms, tool_id)
            ranked.append(
                {
                    "tool_id": tool_id,
                    "score": score,
                    "matched_token_count": len(contributions),
                    "top_token_contributions": contributions[:10],
                }
            )
        ranked.sort(key=lambda row: (-row["score"], row["tool_id"]))
        selected = ranked[: min(top_k, len(ranked))]
        for rank, row in enumerate(selected, start=1):
            row["rank"] = rank
        return {
            "algorithm": self.config["algorithm"],
            "index_sha256": self.index_sha256,
            "top_k": top_k,
            "query_token_count": sum(query_terms.values()),
            "unique_query_token_count": len(query_terms),
            "candidate_pool_size": len(pool_tool_ids),
            "candidates": selected,
        }

    def index_snapshot(self) -> dict[str, Any]:
        rows = []
        for tool_id in sorted(self.entries):
            terms = self.document_terms[tool_id]
            rows.append(
                {
                    "tool_id": tool_id,
                    "weighted_token_count": int(self.document_lengths[tool_id]),
                    "unique_token_count": len(terms),
                    "document_terms_sha256": json_hash(dict(sorted(terms.items()))),
                }
            )
        return {
            "schema_version": "1.0",
            "algorithm": self.config["algorithm"],
            "index_sha256": self.index_sha256,
            "document_count": self.document_count,
            "average_weighted_document_length": round(
                self.average_document_length, 8
            ),
            "vocabulary_size": len(self.document_frequency),
            "documents": rows,
        }
