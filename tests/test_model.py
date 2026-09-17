"""Address parsing and natural ordering (plcdoc.model)."""

import pytest

from plcdoc.model import Address, Variable, parse_address


def test_parse_bit_address():
    addr = parse_address("%IX0.7")
    assert addr == Address(area="I", size="X", path=(0, 7))
    assert addr.byte == 0
    assert addr.bit == 7
    assert addr.direction == "input"


def test_parse_word_address_has_no_bit():
    addr = parse_address("%QW10")
    assert addr == Address(area="Q", size="W", path=(10,))
    assert addr.byte == 10
    assert addr.bit is None
    assert addr.direction == "output"


def test_parse_memory_address():
    assert parse_address("%MX0.0").direction == "memory"


def test_size_defaults_to_bit_and_case_is_normalised():
    assert parse_address("%I0.0") == Address("I", "X", (0, 0))
    assert parse_address("%qx1.2") == Address("Q", "X", (1, 2))
    assert parse_address("  %IW4 ") == Address("I", "W", (4,))


def test_hierarchical_address_keeps_every_part():
    assert parse_address("%IX1.2.3").path == (1, 2, 3)


@pytest.mark.parametrize("bad", ["", "IX0.0", "%ZX0.0", "%IX", "%IX0.", "%IXa.b", "bStart"])
def test_invalid_addresses_raise(bad):
    with pytest.raises(ValueError):
        parse_address(bad)


def test_natural_order_not_string_order():
    addresses = ["%IX1.0", "%IX0.10", "%IX0.7", "%IX0.2"]
    ordered = sorted(addresses, key=lambda a: parse_address(a).sort_key)
    assert ordered == ["%IX0.2", "%IX0.7", "%IX0.10", "%IX1.0"]
    # plain string sort gets it wrong, which is the point of the helper
    assert sorted(addresses) != ordered


def test_order_is_area_then_size_then_byte():
    addresses = ["%MX0.0", "%QW10", "%IW12", "%QX0.4", "%IX1.0", "%IW10", "%QX0.0", "%IX0.7"]
    ordered = sorted(addresses, key=lambda a: parse_address(a).sort_key)
    assert ordered == [
        "%IX0.7",
        "%IX1.0",
        "%IW10",
        "%IW12",
        "%QX0.0",
        "%QX0.4",
        "%QW10",
        "%MX0.0",
    ]


def test_variable_direction_from_address():
    assert Variable("a", "BOOL", "P", "local", address="%IX0.0").direction == "input"
    assert Variable("b", "BOOL", "P", "local", address="%QX0.0").direction == "output"
    assert Variable("c", "BOOL", "P", "local", address="%MW2").direction == "memory"
    assert Variable("d", "BOOL", "P", "local").direction is None
    assert Variable("e", "BOOL", "P", "local", address="garbage").direction is None
    assert Variable("e", "BOOL", "P", "local", address="garbage").parsed_address is None
