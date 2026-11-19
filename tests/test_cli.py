import argparse

import pytest

from h3_indexing.cli import _parse_attr
from h3_indexing.distribution import AttributeType


def test_parse_weighted_attr():
    assert _parse_attr("renda_total:ponderado:populacao") == (
        "renda_total",
        AttributeType.WEIGHTED,
        "populacao",
    )


def test_parse_simple_attr_has_no_weight():
    assert _parse_attr("populacao:extensivo") == (
        "populacao",
        AttributeType.EXTENSIVE,
        None,
    )


@pytest.mark.parametrize(
    "value", ["renda_total:ponderado", "populacao:extensivo:domicilios", "renda"]
)
def test_parse_invalid_attr_raises(value):
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_attr(value)
