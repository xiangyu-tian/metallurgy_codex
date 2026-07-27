"""Explainable lexical candidate-model retrieval for M4.6B experiments."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Iterable, List


RETRIEVAL_STRATEGY = "lexical-card-v1"


# Model-card text is the primary index.  These aliases add domain wording that
# appears in natural-language questions but is not consistently present in the
# frozen card names.
MODEL_TERMS: Dict[str, Dict[str, float]] = {
    "A001": {
        "单位换算": 10, "换算": 8, "转换单位": 8, "摄氏度": 5,
        "开尔文": 5, "华氏度": 5, "mpa": 4, "千克": 3, "kg": 2,
    },
    "A002": {
        "化学式解析": 10, "解析化学式": 10, "解析": 5,
        "元素组成": 7, "原子数": 6, "质量分数": 3,
    },
    "A003": {
        "摩尔质量": 10, "分子量": 9, "相对分子质量": 9,
    },
    "A004": {
        "成分归一化": 10, "组成归一化": 10, "归一化": 8,
        "组分归一": 8,
    },
    "A005": {
        "质量守恒": 10, "元素守恒": 10, "物料衡算": 9,
        "物流": 6, "闭合率": 6, "元素平衡": 8,
    },
    "B001": {
        "shomate": 10, "定压热容": 10, "热容": 7, "cp": 5,
    },
    "B002": {
        "nasa": 10, "nasa 多项式": 12, "多项式热物性": 9,
    },
    "B003": {
        "显热": 10, "焓积分": 10, "显热与焓": 10,
    },
    "B004": {
        "熵积分": 10, "积分熵": 9,
    },
    "B005": {
        "物种 gibbs": 12, "物种吉布斯": 12, "单物种自由能": 10,
        "物种自由能": 10,
    },
    "B006": {
        "反应焓": 12, "反应热": 9, "标准生成焓": 5,
    },
    "B007": {
        "反应熵": 12, "标准反应熵": 12,
    },
    "B008": {
        "反应 gibbs": 12, "反应吉布斯": 12, "反应自由能": 10,
        "反应方向": 8, "自发方向": 8,
    },
    "B009": {
        "平衡常数": 12, "logk": 10, "平衡 k": 8,
    },
    "B019": {
        "杠杆规则": 12, "相分数": 10, "两相分数": 10,
        "两相边界": 7,
    },
    "C001": {
        "arrhenius": 12, "阿伦尼乌斯": 12, "速率常数": 10,
        "指前因子": 6,
    },
    "C002": {
        "扩散系数": 12, "扩散距离": 10, "扩散常数": 8,
        "d0": 5,
    },
}

MODEL_COMPOSITE_TERMS = {
    "B008": [
        (("反应",), ("gibbs", "吉布斯", "自由能"), 10, "反应 + Gibbs/自由能"),
    ],
}

CALCULATION_SIGNALS = (
    "计算", "换算", "转换", "求出", "求 ", "估算", "核对", "校验",
    "判断", "归一化", "解析", "数值", "多少", "积分",
)


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _ordered_unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


class CandidateModelRetriever:
    """Rank frozen model cards using explainable domain-term matches."""

    strategy = RETRIEVAL_STRATEGY

    def __init__(self, registry):
        self.registry = registry
        self.cards = {
            card["model_code"]: deepcopy(card)
            for card in registry.list_models()
        }

    def _terms_for(self, model_code: str) -> Dict[str, float]:
        card = self.cards[model_code]
        terms = dict(MODEL_TERMS.get(model_code, {}))
        for text, weight in (
            (card.get("model_name"), 12),
            (card.get("name"), 12),
            (card.get("api_name"), 7),
            (model_code, 12),
        ):
            normalized = _normalize(text)
            if normalized:
                terms[normalized] = max(weight, terms.get(normalized, 0))
        return terms

    def retrieve(self, query: str, *, top_k: int = 5) -> dict:
        if top_k < 1:
            raise ValueError("top_k 必须大于等于 1")
        normalized_query = _normalize(query)
        ranked = []
        for model_code in sorted(self.cards):
            matched = []
            score = 0.0
            for term, weight in self._terms_for(model_code).items():
                normalized_term = _normalize(term)
                if normalized_term and normalized_term in normalized_query:
                    matched.append(normalized_term)
                    score += float(weight)
            for left_terms, right_terms, weight, label in MODEL_COMPOSITE_TERMS.get(
                model_code,
                [],
            ):
                if (
                    any(_normalize(term) in normalized_query for term in left_terms)
                    and any(
                        _normalize(term) in normalized_query
                        for term in right_terms
                    )
                ):
                    matched.append(label)
                    score += float(weight)
            if score > 0:
                ranked.append({
                    "model_code": model_code,
                    "model_name": self.cards[model_code]["model_name"],
                    "score": round(score, 4),
                    "matched_terms": sorted(
                        set(matched),
                        key=lambda item: (-len(item), item),
                    ),
                })

        ranked.sort(key=lambda item: (-item["score"], item["model_code"]))
        fallback_used = False
        fallback_reason = None
        if ranked:
            candidates = ranked[:top_k]
        elif any(signal in normalized_query for signal in CALCULATION_SIGNALS):
            fallback_used = True
            fallback_reason = "calculation_intent_without_match"
            candidates = [{
                "model_code": model_code,
                "model_name": self.cards[model_code]["model_name"],
                "score": 0.0,
                "matched_terms": [],
            } for model_code in sorted(self.cards)]
        else:
            fallback_reason = "no_tool_signal"
            candidates = []

        for rank, item in enumerate(candidates, start=1):
            item["rank"] = rank
            if item["matched_terms"]:
                item["reason"] = "命中：" + "、".join(item["matched_terms"])
            else:
                item["reason"] = "低置信度计算意图，回退到全部模型"

        return {
            "strategy": self.strategy,
            "query": query,
            "top_k": top_k,
            "candidate_models": candidates,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "matched_model_count": len(ranked),
            "total_model_count": len(self.cards),
        }


def evaluate_candidate_retrieval(dataset, retriever, *, top_k: int = 5) -> dict:
    """Evaluate retrieval separately from LLM tool-use decisions."""

    rows = []
    required_tool_count = 0
    hit_tool_count = 0
    for case in dataset.list_cases():
        retrieval = retriever.retrieve(case["question"], top_k=top_k)
        candidate_codes = [
            item["model_code"] for item in retrieval["candidate_models"]
        ]
        required_models = (
            _ordered_unique(case.get("expected_call_sequence", []))
            if case["should_call_tool"]
            else []
        )
        hits = [code for code in required_models if code in candidate_codes]
        required_tool_count += len(required_models)
        hit_tool_count += len(hits)
        recall = len(hits) / len(required_models) if required_models else None
        complete = (
            set(required_models).issubset(candidate_codes)
            if required_models
            else None
        )
        precision = (
            len(hits) / len(candidate_codes)
            if required_models and candidate_codes
            else (0.0 if required_models else None)
        )
        ranks = [
            candidate_codes.index(code) + 1
            for code in required_models
            if code in candidate_codes
        ]
        rows.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "should_call_tool": case["should_call_tool"],
            "required_models": required_models,
            "candidate_models": candidate_codes,
            "candidate_count": len(candidate_codes),
            "candidate_recall": recall,
            "complete_recall": complete,
            "candidate_precision": precision,
            "best_required_rank": min(ranks) if ranks else None,
            "fallback_used": retrieval["fallback_used"],
            "fallback_reason": retrieval["fallback_reason"],
        })

    tool_rows = [row for row in rows if row["required_models"]]
    single_rows = [
        row for row in tool_rows if len(row["required_models"]) == 1
    ]
    multi_rows = [
        row for row in rows if row["category"] == "multi_tool"
    ]
    summary = {
        "case_count": len(rows),
        "tool_required_case_count": len(tool_rows),
        "micro_candidate_recall": (
            hit_tool_count / required_tool_count
            if required_tool_count
            else None
        ),
        "tool_required_complete_recall": (
            sum(bool(row["complete_recall"]) for row in tool_rows) / len(tool_rows)
            if tool_rows
            else None
        ),
        "single_required_complete_recall": (
            sum(bool(row["complete_recall"]) for row in single_rows)
            / len(single_rows)
            if single_rows
            else None
        ),
        "multi_tool_complete_recall": (
            sum(bool(row["complete_recall"]) for row in multi_rows)
            / len(multi_rows)
            if multi_rows
            else None
        ),
        "average_candidate_precision": (
            sum(row["candidate_precision"] for row in tool_rows) / len(tool_rows)
            if tool_rows
            else None
        ),
        "average_candidate_count": (
            sum(row["candidate_count"] for row in rows) / len(rows)
            if rows
            else 0.0
        ),
        "fallback_rate": (
            sum(row["fallback_used"] for row in rows) / len(rows)
            if rows
            else 0.0
        ),
    }
    return {
        "strategy": retriever.strategy,
        "dataset_version": dataset.version,
        "top_k": top_k,
        "summary": summary,
        "results": rows,
    }
