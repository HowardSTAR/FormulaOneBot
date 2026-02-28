"""
Тесты функций f1_data.
"""
import pandas as pd
import pytest

from app.f1_data import sort_standings_zero_last


def test_sort_standings_zero_last_normal():
    """sort_standings_zero_last — обычная сортировка по позициям."""
    df = pd.DataFrame([
        {"position": 2, "points": 50},
        {"position": 1, "points": 100},
        {"position": 3, "points": 30},
    ])
    result = sort_standings_zero_last(df, "position")
    assert list(result["position"]) == [1, 2, 3]


def test_sort_standings_zero_last_zero_last():
    """sort_standings_zero_last — пилоты с 0/NaN в конце."""
    df = pd.DataFrame([
        {"position": 0, "points": 0},
        {"position": 1, "points": 100},
        {"position": float("nan"), "points": 0},
        {"position": 2, "points": 50},
    ])
    result = sort_standings_zero_last(df, "position")
    # 1 и 2 должны быть первыми
    first_positions = list(result["position"].head(2))
    assert 1 in first_positions
    assert 2 in first_positions
    # 0 и NaN в конце
    last_positions = list(result["position"].tail(2))
    assert 0 in last_positions or any(pd.isna(p) for p in last_positions)


def test_sort_standings_zero_last_empty():
    """sort_standings_zero_last — пустой DataFrame."""
    df = pd.DataFrame(columns=["position", "points"])
    result = sort_standings_zero_last(df)
    assert result.empty


def test_sort_standings_zero_last_none_handling():
    """sort_standings_zero_last — None/отсутствие колонки."""
    assert sort_standings_zero_last(None) is None
    df = pd.DataFrame([{"x": 1}])
    result = sort_standings_zero_last(df, "position")
    assert result is not None
    assert len(result) == 1
