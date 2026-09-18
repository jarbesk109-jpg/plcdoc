from pathlib import Path

import pytest

from plcdoc import parse_file

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

SMALL_V1 = SAMPLES / "01_conveyor_v1.xml"
SMALL_V2 = SAMPLES / "02_conveyor_v2.xml"
LARGE = SAMPLES / "03_line_large.xml"
TYPES_QUALIFIERS = SAMPLES / "04_types_qualifiers.xml"
DRIVE_OOP = SAMPLES / "05_drive_oop.xml"


def relabel_object_ids(root):
    """Replace every ObjectId in *root* in place, consistently, and return *root*.

    CODESYS writes the same GUID as ``<ObjectId>`` text on an object and as an
    ``ObjectId`` attribute in ``ProjectStructure`` (and on ``Method`` /
    ``Property``). One old -> new map is applied to both forms, so joins keep
    resolving while no original GUID survives. Tests use it to prove GUIDs are
    noise for the model (Decision 010).
    """
    mapping: dict[str, str] = {}

    def renamed(old: str) -> str:
        if old not in mapping:
            mapping[old] = f"00000000-0000-4000-8000-{len(mapping):012d}"
        return mapping[old]

    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue
        if elem.tag.rpartition("}")[2] == "ObjectId" and elem.text and elem.text.strip():
            elem.text = renamed(elem.text.strip())
        if "ObjectId" in elem.attrib:
            elem.set("ObjectId", renamed(elem.attrib["ObjectId"]))
    return root


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


@pytest.fixture(scope="session")
def drive_oop():
    return parse_file(DRIVE_OOP)
