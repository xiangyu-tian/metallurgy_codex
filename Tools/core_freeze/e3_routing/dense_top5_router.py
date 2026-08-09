"""Frozen local dense retriever over the bound tool-contract registry."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from fastembed import TextEmbedding


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parameter_rows(parameters: dict[str, Any]) -> list[str]:
    rows: list[str] = []

    def visit(schema: Any, prefix: str = "") -> None:
        if not isinstance(schema, dict):
            return
        required = set(schema.get("required", []))
        for name, child in sorted(schema.get("properties", {}).items()):
            qualified = f"{prefix}.{name}" if prefix else name
            if isinstance(child, dict):
                description = str(child.get("description", "")).strip()
                type_name = str(child.get("type", "")).strip()
                marker = "必需" if name in required else "可选"
                rows.append(
                    f"{qualified}（{marker}；类型={type_name or '未声明'}）：{description}"
                )
                visit(child, qualified)

    visit(parameters)
    return rows


def render_tool_document(entry: dict[str, Any], field_order: list[str]) -> str:
    function = entry.get("openai_tool", {}).get("function", {})
    values = {
        "tool_name": str(entry.get("tool_name", "")),
        "semantic_alias": str(entry.get("semantic_alias", "")),
        "scenario": str(entry.get("scenario", "")),
        "tool_type": str(entry.get("tool_type", "")),
        "core_method": str(entry.get("core_method", "")),
        "main_input": str(entry.get("main_input", "")),
        "main_output": str(entry.get("main_output", "")),
        "applicable_boundary_risk": str(entry.get("applicable_boundary_risk", "")),
        "function_description": str(function.get("description", "")),
        "parameter_name_and_description": "；".join(
            _parameter_rows(function.get("parameters", {}))
        ),
    }
    labels = {
        "tool_name": "工具名称",
        "semantic_alias": "语义别名",
        "scenario": "领域场景",
        "tool_type": "工具类型",
        "core_method": "核心方法",
        "main_input": "主要输入",
        "main_output": "主要输出",
        "applicable_boundary_risk": "适用边界与风险",
        "function_description": "函数说明",
        "parameter_name_and_description": "参数名称与说明",
    }
    unknown = set(field_order) - set(values)
    if unknown:
        raise ValueError(f"unknown dense document fields: {sorted(unknown)}")
    return "\n".join(
        f"{labels[field]}：{values[field]}" for field in field_order if values[field]
    )


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    array = np.asarray(matrix, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if np.any(norms <= 0):
        raise ValueError("dense embedding contains a zero vector")
    return np.ascontiguousarray(array / norms, dtype=np.float32)


def vectors_sha256(tool_ids: list[str], vectors: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(canonical_json(tool_ids).encode("utf-8"))
    digest.update(np.asarray(vectors, dtype="<f4").tobytes(order="C"))
    return digest.hexdigest()


class FrozenDenseTop5:
    """CPU-only BGE retrieval with a hash-bound local model snapshot."""

    def __init__(
        self,
        entries: Iterable[dict[str, Any]],
        config: dict[str, Any],
        model_snapshot_path: Path,
    ):
        self.config = deepcopy(config)
        rows = sorted((deepcopy(row) for row in entries), key=lambda row: row["tool_id"])
        self.entries = {row["tool_id"]: row for row in rows}
        if not rows:
            raise ValueError("dense index requires at least one tool")
        if len(self.entries) != len(rows):
            raise ValueError("tool registry contains duplicate IDs")
        self.tool_ids = [row["tool_id"] for row in rows]
        fields = config["document_renderer"]["field_order"]
        self.documents = [render_tool_document(row, fields) for row in rows]
        model = config["embedding_model"]
        self.encoder = TextEmbedding(
            model_name=model["public_model_id"],
            specific_model_path=str(model_snapshot_path.resolve()),
            local_files_only=True,
            providers=[model["provider"]],
            threads=int(model["threads"]),
        )
        vectors = list(
            self.encoder.passage_embed(
                self.documents, batch_size=int(model["batch_size"])
            )
        )
        self.vectors = l2_normalize(np.vstack(vectors))
        expected_shape = (len(rows), int(model["dimension"]))
        if self.vectors.shape != expected_shape:
            raise ValueError(
                f"unexpected dense matrix shape: {self.vectors.shape} != {expected_shape}"
            )
        self.vector_sha256 = vectors_sha256(self.tool_ids, self.vectors)
        self.document_sha256 = hashlib.sha256(
            canonical_json(dict(zip(self.tool_ids, self.documents))).encode("utf-8")
        ).hexdigest()
        self._row_by_tool_id = {
            tool_id: index for index, tool_id in enumerate(self.tool_ids)
        }

    def embed_query(self, query: str) -> np.ndarray:
        prefix = self.config["query"]["instruction_prefix"]
        vector = next(
            self.encoder.query_embed(
                f"{prefix}{query}",
                batch_size=int(self.config["embedding_model"]["batch_size"]),
            )
        )
        normalized = l2_normalize(np.asarray(vector, dtype=np.float32))[0]
        if normalized.shape != (int(self.config["embedding_model"]["dimension"]),):
            raise ValueError("query embedding has unexpected dimension")
        return normalized

    def rank_vector(
        self, query_vector: np.ndarray, pool_tool_ids: list[str], *, top_k: int = 5
    ) -> dict[str, Any]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if len(pool_tool_ids) != len(set(pool_tool_ids)):
            raise ValueError("candidate pool contains duplicate tool IDs")
        missing = [tool_id for tool_id in pool_tool_ids if tool_id not in self.entries]
        if missing:
            raise ValueError(f"candidate pool contains unindexed tools: {missing}")
        query = l2_normalize(query_vector)[0]
        ranked = []
        for tool_id in pool_tool_ids:
            score = float(np.dot(query, self.vectors[self._row_by_tool_id[tool_id]]))
            ranked.append({"tool_id": tool_id, "score": round(score, 8)})
        ranked.sort(key=lambda row: (-row["score"], row["tool_id"]))
        selected = ranked[: min(top_k, len(ranked))]
        for rank, row in enumerate(selected, start=1):
            row["rank"] = rank
        return {
            "algorithm": self.config["algorithm"],
            "vector_sha256": self.vector_sha256,
            "document_sha256": self.document_sha256,
            "top_k": top_k,
            "candidate_pool_size": len(pool_tool_ids),
            "candidates": selected,
        }

    def retrieve(self, query: str, pool_tool_ids: list[str], *, top_k: int = 5) -> dict[str, Any]:
        return self.rank_vector(self.embed_query(query), pool_tool_ids, top_k=top_k)

    def index_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "algorithm": self.config["algorithm"],
            "model_id": self.config["embedding_model"]["public_model_id"],
            "model_revision": self.config["embedding_model"]["snapshot_revision"],
            "document_count": len(self.tool_ids),
            "embedding_dimension": int(self.vectors.shape[1]),
            "document_sha256": self.document_sha256,
            "vector_sha256": self.vector_sha256,
            "documents": [
                {
                    "tool_id": tool_id,
                    "document_sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
                    "token_count": int(self.encoder.token_count(document)),
                }
                for tool_id, document in zip(self.tool_ids, self.documents)
            ],
        }
