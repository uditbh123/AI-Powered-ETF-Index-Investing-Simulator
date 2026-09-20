"""FinBERT sentiment scoring over headlines.

The model (default ``ProsusAI/finbert``, a BERT finetuned on financial news)
is loaded lazily on first use so the API server and the unit tests never pay
the model-download cost unless scoring is actually requested.

Score mapping
-------------
FinBERT discriminates three classes (positive / negative / neutral). We
collapse them to a single value in [-1, 1] as

    score = P(positive) - P(negative)

which keeps the output calibrated (-1 fully negative, +1 fully positive,
0 neutral or balanced) and symmetric around zero like a volatility
adjustment term. Label name lookup is done via ``config.id2label`` so the
score survives reordered/renamed labels across FinBERT checkpoints.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

log = logging.getLogger(__name__)

_pipeline: tuple[Any, Any] | None = None  # (tokenizer, model)
_device: str | None = None


def _resolve_device() -> str:
    global _device
    if _device is None:
        try:
            import torch

            _device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001 - torch optional at import time
            _device = "cpu"
    return _device


def load_pipeline() -> tuple[Any, Any]:
    """Load (tokenizer, model) once and cache them. Downloads on first call."""
    global _pipeline
    if _pipeline is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        from ..config import settings

        log.info("Loading FinBERT model %s (first run downloads it)...", settings.sentiment_model)
        tokenizer = AutoTokenizer.from_pretrained(settings.sentiment_model)
        model = AutoModelForSequenceClassification.from_pretrained(settings.sentiment_model)
        model.eval()
        _pipeline = (tokenizer, model)
    return _pipeline


def _id2label(model: Any) -> dict[int, str]:
    try:
        return dict(model.config.id2label)
    except Exception:  # noqa: BLE001
        return {i: str(i) for i in range(model.config.num_labels)}


def _label_index(label_map: dict[int, str], needle: str) -> int | None:
    for idx, name in label_map.items():
        if needle in name.lower():
            return idx
    return None


def _softmax(rows: Any) -> Any:
    import torch

    return torch.softmax(rows, dim=1)


def _scores_from_logits(
    logits: Any,
    label_map: dict[int, str],
) -> list[float]:
    pos_idx = _label_index(label_map, "positive")
    neg_idx = _label_index(label_map, "negative")
    if pos_idx is None or neg_idx is None:  # unknown label scheme -> pos before neg
        pos_idx, neg_idx = 0, 1

    probs = _softmax(logits)
    scores = (probs[:, pos_idx] - probs[:, neg_idx]).cpu().numpy().tolist()
    return scores


def score_texts(texts: Sequence[str], batch_size: int | None = None) -> list[float]:
    """Score a list of headlines to [-1, 1]. Empty input -> empty output."""
    texts = [t for t in texts if t and not t.isspace()]
    if not texts:
        return []

    import torch

    from ..config import settings

    tokenizer, model = load_pipeline()
    device = _resolve_device()
    model = model.to(device)
    batch_size = batch_size or settings.sentiment_batch_size
    label_map = _id2label(model)

    scores: list[float] = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            encoded = tokenizer(
                chunk,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(device)
            outputs = model(**encoded)
            scores.extend(_scores_from_logits(outputs.logits, label_map))
    return scores


__all__ = ["load_pipeline", "score_texts"]