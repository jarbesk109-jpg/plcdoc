from pathlib import Path

import pytest

from plcdoc import parse_file

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

SMALL_V1 = SAMPLES / "01_conveyor_v1.xml"
SMALL_V2 = SAMPLES / "02_conveyor_v2.xml"
LARGE = SAMPLES / "03_line_large.xml"
TYPES_QUALIFIERS = SAMPLES / "04_types_qualifiers.xml"


@pytest.fixture(scope="session")
def small():
    return parse_file(SMALL_V1)


@pytest.fixture(scope="session")
def small_v2():
    return parse_file(SMALL_V2)


@pytest.fixture(scope="session")
def large():
    return parse_file(LARGE)


@pytest.fixture(scope="session")
def types_qualifiers():
    return parse_file(TYPES_QUALIFIERS)
