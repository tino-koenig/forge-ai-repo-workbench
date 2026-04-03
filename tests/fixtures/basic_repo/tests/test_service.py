import pytest

from src.service import compute_price


def test_compute_price_happy_path():
    assert compute_price(100.0, 0.1) == 90.0


def test_compute_price_negative_amount():
    with pytest.raises(ValueError):
        compute_price(-1.0)
