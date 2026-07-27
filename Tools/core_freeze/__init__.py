"""Core Frozen statistical input and contrast utilities."""

from .analysis_core import AnalysisValidationError, validate_document
from .build_paired_contrasts import (
    aggregate_pool_repeats,
    build_h3_pairs,
    build_h4_method_contrasts,
    build_h4_scale_pairs,
)

__all__ = [
    "AnalysisValidationError",
    "aggregate_pool_repeats",
    "build_h3_pairs",
    "build_h4_method_contrasts",
    "build_h4_scale_pairs",
    "validate_document",
]
