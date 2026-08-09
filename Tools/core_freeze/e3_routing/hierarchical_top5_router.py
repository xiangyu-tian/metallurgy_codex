"""Deterministic contract hierarchy routing over frozen tool-card metadata."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Iterable

from Tools.core_freeze.e3_routing.lexical_top5_router import (
    WeightedUnicodeNgramBM25,
    canonical_json,
    tokenize,
    tool_fields,
)


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _node_id(prefix: str, *parts: str) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _group_score(
    tool_ids: list[str],
    base_scores: dict[str, float],
    *,
    mean_top_n: int,
    mean_weight: float,
) -> float:
    values = sorted((base_scores[tool_id] for tool_id in tool_ids), reverse=True)
    top = values[:mean_top_n]
    return round(max(values) + mean_weight * sum(top) / len(top), 8)


class ContractHierarchyTop5:
    """Route through scenario, capability and applicability before tool rank."""

    def __init__(
        self,
        entries: Iterable[dict[str, Any]],
        hierarchical_config: dict[str, Any],
        lexical_config: dict[str, Any],
    ):
        rows = [deepcopy(row) for row in entries]
        self.entries = {row["tool_id"]: row for row in rows}
        if not self.entries or len(self.entries) != len(rows):
            raise ValueError("hierarchical registry is empty or contains duplicate IDs")
        self.config = deepcopy(hierarchical_config)
        self.lexical_config = deepcopy(lexical_config)
        self.lexical = WeightedUnicodeNgramBM25(rows, lexical_config)
        self.tool_nodes: dict[str, dict[str, Any]] = {}
        domain_members: dict[str, list[str]] = defaultdict(list)
        capability_members: dict[str, list[str]] = defaultdict(list)
        self.domain_labels: dict[str, str] = {}
        self.capability_labels: dict[str, dict[str, str]] = {}
        for tool_id, entry in sorted(self.entries.items()):
            domain_label = str(entry.get("scenario") or "未分类")
            capability_label = str(entry.get("core_method") or "未声明能力")
            domain_id = _node_id("domain", domain_label)
            capability_id = _node_id(
                "capability", domain_label, capability_label
            )
            domain_members[domain_id].append(tool_id)
            capability_members[capability_id].append(tool_id)
            self.domain_labels[domain_id] = domain_label
            self.capability_labels[capability_id] = {
                "domain_id": domain_id,
                "label": capability_label,
            }
            self.tool_nodes[tool_id] = {
                "domain_id": domain_id,
                "capability_id": capability_id,
                "applicability_signature_sha256": json_hash(
                    {
                        "main_input": entry.get("main_input"),
                        "main_output": entry.get("main_output"),
                        "applicable_boundary_risk": entry.get(
                            "applicable_boundary_risk"
                        ),
                        "parameters": entry["openai_tool"]["function"].get(
                            "parameters", {}
                        ),
                    }
                ),
            }
        self.domain_members = {
            key: sorted(value) for key, value in domain_members.items()
        }
        self.capability_members = {
            key: sorted(value) for key, value in capability_members.items()
        }
        self.taxonomy_sha256 = json_hash(
            {
                "hierarchy": hierarchical_config["hierarchy"],
                "tool_nodes": self.tool_nodes,
                "domain_members": self.domain_members,
                "capability_members": self.capability_members,
            }
        )

    def _idf(self, token: str) -> float:
        df = self.lexical.document_frequency.get(token, 0)
        count = self.lexical.document_count
        return math.log(1.0 + (count - df + 0.5) / (df + 0.5))

    def _applicability_overlap(self, query_tokens: Counter[str], tool_id: str) -> float:
        fields = tool_fields(self.entries[tool_id])
        values = []
        for field in (
            "main_input",
            "main_output",
            "applicable_boundary_risk",
            "parameter_name",
            "parameter_description",
        ):
            values.extend(fields[field])
        contract_tokens = {
            token
            for value in values
            for token in tokenize(value, self.lexical_config["tokenizer"])
        }
        score = sum(
            self._idf(token) * (1.0 + math.log(float(frequency)))
            for token, frequency in query_tokens.items()
            if token in contract_tokens
        )
        return round(score, 8)

    def retrieve(
        self, query: str, pool_tool_ids: list[str], *, top_k: int = 5
    ) -> dict[str, Any]:
        if top_k != self.config["top_k"]:
            raise ValueError("hierarchical router only supports its frozen Top-K")
        if len(pool_tool_ids) != len(set(pool_tool_ids)):
            raise ValueError("candidate pool contains duplicate tool IDs")
        missing = [tool_id for tool_id in pool_tool_ids if tool_id not in self.entries]
        if missing:
            raise ValueError(f"candidate pool contains unindexed tools: {missing}")
        base = self.lexical.retrieve(query, pool_tool_ids, top_k=len(pool_tool_ids))
        base_scores = {row["tool_id"]: row["score"] for row in base["candidates"]}

        pool_domains: dict[str, list[str]] = defaultdict(list)
        pool_capabilities: dict[str, list[str]] = defaultdict(list)
        for tool_id in pool_tool_ids:
            node = self.tool_nodes[tool_id]
            pool_domains[node["domain_id"]].append(tool_id)
            pool_capabilities[node["capability_id"]].append(tool_id)
        domain_rows = []
        for domain_id, members in pool_domains.items():
            domain_rows.append(
                {
                    "domain_id": domain_id,
                    "domain_label": self.domain_labels[domain_id],
                    "member_count": len(members),
                    "score": _group_score(
                        members,
                        base_scores,
                        mean_top_n=self.config["group_mean_top_n"],
                        mean_weight=self.config["group_mean_weight"],
                    ),
                }
            )
        domain_rows.sort(key=lambda row: (-row["score"], row["domain_id"]))
        selected_domains = domain_rows[: self.config["domain_top_n"]]
        selected_domain_ids = {row["domain_id"] for row in selected_domains}
        domain_score_by_id = {row["domain_id"]: row["score"] for row in domain_rows}

        capability_rows = []
        for capability_id, members in pool_capabilities.items():
            meta = self.capability_labels[capability_id]
            if meta["domain_id"] not in selected_domain_ids:
                continue
            capability_rows.append(
                {
                    "capability_id": capability_id,
                    "domain_id": meta["domain_id"],
                    "capability_label": meta["label"],
                    "member_count": len(members),
                    "score": _group_score(
                        members,
                        base_scores,
                        mean_top_n=self.config["group_mean_top_n"],
                        mean_weight=self.config["group_mean_weight"],
                    ),
                }
            )
        capability_rows.sort(
            key=lambda row: (-row["score"], row["capability_id"])
        )
        selected_capabilities = capability_rows[: self.config["capability_top_n"]]
        selected_capability_ids = {
            row["capability_id"] for row in selected_capabilities
        }
        capability_score_by_id = {
            row["capability_id"]: row["score"] for row in capability_rows
        }

        pruned_tool_ids = [
            tool_id
            for tool_id in pool_tool_ids
            if self.tool_nodes[tool_id]["capability_id"] in selected_capability_ids
        ]
        backfilled = []
        if len(pruned_tool_ids) < top_k:
            selected_domain_tools = sorted(
                (
                    tool_id
                    for tool_id in pool_tool_ids
                    if self.tool_nodes[tool_id]["domain_id"] in selected_domain_ids
                    and tool_id not in pruned_tool_ids
                ),
                key=lambda tool_id: (-base_scores[tool_id], tool_id),
            )
            for tool_id in selected_domain_tools:
                if len(pruned_tool_ids) >= top_k:
                    break
                pruned_tool_ids.append(tool_id)
                backfilled.append(tool_id)
        if len(pruned_tool_ids) < top_k:
            global_tools = sorted(
                (tool_id for tool_id in pool_tool_ids if tool_id not in pruned_tool_ids),
                key=lambda tool_id: (-base_scores[tool_id], tool_id),
            )
            for tool_id in global_tools:
                if len(pruned_tool_ids) >= top_k:
                    break
                pruned_tool_ids.append(tool_id)
                backfilled.append(tool_id)

        weights = self.config["final_score_weights"]
        query_tokens = Counter(tokenize(query, self.lexical_config["tokenizer"]))
        final_rows = []
        for tool_id in pruned_tool_ids:
            node = self.tool_nodes[tool_id]
            domain_score = domain_score_by_id[node["domain_id"]]
            capability_score = capability_score_by_id.get(
                node["capability_id"], base_scores[tool_id]
            )
            applicability = self._applicability_overlap(query_tokens, tool_id)
            final_score = (
                weights["base_lexical"] * base_scores[tool_id]
                + weights["domain"] * domain_score
                + weights["capability"] * capability_score
                + weights["applicability_overlap"] * applicability
            )
            final_rows.append(
                {
                    "tool_id": tool_id,
                    "score": round(final_score, 8),
                    "base_lexical_score": base_scores[tool_id],
                    "domain_score": domain_score,
                    "capability_score": capability_score,
                    "applicability_overlap_score": applicability,
                    "domain_id": node["domain_id"],
                    "capability_id": node["capability_id"],
                    "backfilled": tool_id in backfilled,
                }
            )
        final_rows.sort(key=lambda row: (-row["score"], row["tool_id"]))
        candidates = final_rows[:top_k]
        for rank, row in enumerate(candidates, start=1):
            row["rank"] = rank
        return {
            "algorithm": self.config["algorithm"],
            "taxonomy_sha256": self.taxonomy_sha256,
            "lexical_index_sha256": self.lexical.index_sha256,
            "candidate_pool_size": len(pool_tool_ids),
            "selected_domains": selected_domains,
            "selected_capabilities": selected_capabilities,
            "pruned_tool_count": len(pruned_tool_ids),
            "backfilled_tool_ids": backfilled,
            "candidates": candidates,
        }

    def taxonomy_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "algorithm": self.config["algorithm"],
            "taxonomy_sha256": self.taxonomy_sha256,
            "tool_count": len(self.tool_nodes),
            "domain_count": len(self.domain_members),
            "capability_count": len(self.capability_members),
            "domains": [
                {
                    "domain_id": domain_id,
                    "domain_label": self.domain_labels[domain_id],
                    "tool_ids": members,
                }
                for domain_id, members in sorted(self.domain_members.items())
            ],
            "capabilities": [
                {
                    "capability_id": capability_id,
                    **self.capability_labels[capability_id],
                    "tool_ids": members,
                }
                for capability_id, members in sorted(self.capability_members.items())
            ],
            "tool_nodes": [
                {"tool_id": tool_id, **node}
                for tool_id, node in sorted(self.tool_nodes.items())
            ],
        }
