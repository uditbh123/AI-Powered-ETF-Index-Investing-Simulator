"""Tests for FinBERT scoring logic (mock model, never downloads weights)."""
from __future__ import annotations

import types

import pytest

torch = pytest.importorskip("torch")  # skip whole module when torch is absent

from app.services import sentiment


class FakeEncoding(dict):
    def to(self, device):
        for key, value in self.items():
            if hasattr(value, "to"):
                self[key] = value.to(device)
        return self


class FakeTokenizer:
    def __call__(self, texts, **kwargs):
        batch = len(texts)
        return FakeEncoding(input_ids=torch.zeros((batch, 3), dtype=torch.long))


class FakeModel:
    def __init__(self, id2label=None, pos_col=0, neg_col=1):
        self.config = types.SimpleNamespace(
            num_labels=3,
            id2label=id2label or {0: "positive", 1: "negative", 2: "neutral"},
        )
        self.pos_col = pos_col
        self.neg_col = neg_col

    def eval(self):
        return self

    def to(self, device):
        return self

    def __call__(self, **encoded):
        batch = encoded["input_ids"].shape[0]
        logits = torch.full((batch, 3), -2.0)
        logits[:, self.pos_col] = 3.0
        logits[:, self.neg_col] = -3.0
        return types.SimpleNamespace(logits=logits)


def _fake_pipeline(model=None):
    def load():
        return FakeTokenizer(), model or FakeModel()
    return load


def test_label_index_finds_labels_regardless_of_order():
    labels = {0: "neutral", 1: "negative", 2: "positive"}
    assert sentiment._label_index(labels, "positive") == 2
    assert sentiment._label_index(labels, "negative") == 1
    assert sentiment._label_index(labels, "nonsense") is None


def test_scores_from_logits_default_label_scheme():
    # id2label 0=positive, 1=negative, 2=neutral (ProsusAI/finbert layout)
    logits = torch.tensor([[3.0, -3.0, 0.0], [-3.0, 3.0, 0.0]])
    labels = {0: "positive", 1: "negative", 2: "neutral"}
    scores = sentiment._scores_from_logits(logits, labels)
    assert scores[0] > 0.9
    assert scores[1] < -0.9


def test_scores_from_logits_reordered_labels():
    # 3 logits columns, labels reordered compared to ProsusAI layout
    logits = torch.tensor([[0.0, 0.0, 3.0]])  # col2 carries the positivity
    labels = {0: "negative", 1: "neutral", 2: "positive"}
    scores = sentiment._scores_from_logits(logits, labels)
    assert sentiment._label_index(labels, "positive") == 2
    assert sentiment._label_index(labels, "negative") == 0
    assert scores[0] > 0.8


def test_score_texts_positive_headline(monkeypatch):
    monkeypatch.setattr(sentiment, "load_pipeline", _fake_pipeline())
    scores = sentiment.score_texts(["Stocks surge to new highs"])
    assert len(scores) == 1
    assert scores[0] > 0


def test_score_texts_empty_input(monkeypatch):
    monkeypatch.setattr(sentiment, "load_pipeline", _fake_pipeline())
    assert sentiment.score_texts([]) == []
    assert sentiment.score_texts(["", "  ", " \t "]) == []


def test_score_texts_batches(monkeypatch):
    monkeypatch.setattr(sentiment, "load_pipeline", _fake_pipeline())
    scores = sentiment.score_texts(
        [f"Headline {i}" for i in range(17)],
        batch_size=5,
    )
    assert len(scores) == 17
    assert all(s > 0 for s in scores)


def test_score_texts_respects_reordered_labels(monkeypatch):
    model = FakeModel(id2label={0: "negative", 1: "neutral", 2: "positive"}, pos_col=2)
    monkeypatch.setattr(sentiment, "load_pipeline", _fake_pipeline(model))
    scores = sentiment.score_texts(["Whatever the headline says"])
    assert scores[0] > 0