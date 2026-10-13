from decimal import Decimal

import pytest

from app.catalog.normalize import (
    MeasurementError,
    build_search_text,
    grams_from,
    grams_to,
    ml_from,
    normalize_text,
    parse_weight_text,
    slugify,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Arc'teryx", "arcteryx"),
        ("ARCTERYX", "arcteryx"),
        ("Sea to Summit", "sea to summit"),
        ("Fjällräven", "fjallraven"),
        ("Black Diamond — Spot 400", "black diamond spot 400"),
        ("REI Co-op", "rei co op"),
        ("2.5 L", "2.5 l"),
        ("A&B", "a and b"),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


def test_slugify_is_stable():
    assert slugify("Copper Spur HV UL2") == "copper-spur-hv-ul2"
    assert slugify("Tensor™ All-Season") == "tensortm-all-season" or slugify(
        "Tensor™ All-Season"
    ).startswith("tensor")


@pytest.mark.parametrize(
    "text, grams",
    [
        ("505 g", Decimal("505.000")),
        ("1.2 kg", Decimal("1200.000")),
        ("14.1 oz", Decimal("399.728")),
        ("2 lb 3 oz", Decimal("992.233")),
        ("1 lb, 2 oz", Decimal("510.291")),
        ("3 lbs", Decimal("1360.777")),
    ],
)
def test_parse_weight_text(text, grams):
    assert parse_weight_text(text) == grams


@pytest.mark.parametrize("text", ["", "about a pound", "12 stone", "oz"])
def test_parse_weight_text_rejects_garbage(text):
    with pytest.raises(MeasurementError):
        parse_weight_text(text)


def test_round_trip_does_not_drift():
    # A user typing 12.5 oz must see 12.5 oz again, not 12.49 or 12.51.
    grams = grams_from("12.5", "oz")
    assert round(grams_to(grams, "oz"), 2) == Decimal("12.50")
    grams = grams_from("2.65", "lb")
    assert round(grams_to(grams, "lb"), 3) == Decimal("2.650")


def test_volume_conversions():
    assert ml_from("58", "l") == Decimal("58000.0")
    assert ml_from("3600", "cu_in") == Decimal("58993.4")
    assert ml_from("32", "fl_oz") == Decimal("946.4")
    with pytest.raises(MeasurementError):
        ml_from("0", "l")


def test_negative_and_non_numeric_rejected():
    with pytest.raises(MeasurementError):
        grams_from("-1", "g")
    with pytest.raises(MeasurementError):
        grams_from("NaN", "g")
    with pytest.raises(MeasurementError):
        grams_from(True, "g")


def test_build_search_text_dedupes_and_normalizes():
    assert (
        build_search_text("Arc'teryx", "Arcteryx", "Beta AR", None, "Rainwear")
        == "arcteryx beta ar rainwear"
    )
