"""Sample 05 (ENUM, STRUCT, FB method/action/property) and the M3a parser changes.

Facts are checked against ``samples/05_drive_oop.xml``; shapes no export
contains are SYNTHETIC mutations of a parsed sample, marked as such.
"""

from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from plcdoc import Attribute, EnumValue
from plcdoc.parser import parse_element

from conftest import DRIVE_OOP, LARGE, relabel_object_ids

NS = {"p": "http://www.plcopen.org/xml/tc6_0200"}
PREFIX = "{" + NS["p"] + "}"
ENUM = ".//p:dataType[@name='E_DriveState']"
STRUCT = ".//p:dataType[@name='ST_Drive']"
OWNER = ("Device", "Application")


def _data_type(project, name):
    return next(d for d in project.data_types if d.name == name)


# --------------------------------------------------------------------------- #
# Commit 2: one ownership walk
# --------------------------------------------------------------------------- #


def test_walk_gives_pou_gvl_and_task_the_same_owner():
    """POUs, GVLs and tasks under a second resource all report that resource."""
    root = ET.parse(LARGE).getroot()
    configuration = root.find(".//p:configuration", NS)
    second = deepcopy(configuration.find("p:resource", NS))
    second.set("name", "Application2")
    configuration.append(second)
    project = parse_element(root)
    owners = {
        (kind, obj.name): (obj.configuration, obj.application)
        for kind, objects in (("pou", project.pous), ("gvl", project.gvls), ("task", project.tasks))
        for obj in objects
        if obj.application == "Application2"
    }
    assert owners == {
        ("pou", "PLC_PRG"): ("Device", "Application2"),
        ("pou", "FB_Motor"): ("Device", "Application2"),
        ("pou", "FC_Scale"): ("Device", "Application2"),
        ("pou", "PRG_Alarm"): ("Device", "Application2"),
        ("gvl", "GVL_IO"): ("Device", "Application2"),
        ("task", "MainTask"): ("Device", "Application2"),
    }
    assert project.warnings == []


def _object_ids(root):
    """Every ObjectId in the tree: text form and attribute form, in document order."""
    texts, attributes = [], []
    for elem in root.iter():
        if elem.tag == PREFIX + "ObjectId":
            texts.append(elem.text.strip())
        if "ObjectId" in elem.attrib:
            attributes.append(elem.attrib["ObjectId"])
    return texts, attributes


def test_relabel_object_ids_helper():
    """A no-op helper would pass every GUID-noise test; prove it really relabels."""
    root = ET.parse(DRIVE_OOP).getroot()
    texts_before, attributes_before = _object_ids(root)
    originals = set(texts_before) | set(attributes_before)
    # configuration, resource, task, 2 DUTs, 2 POUs, action, method, property, Libraries;
    # ProjectStructure reuses the same GUIDs.
    assert len(originals) == 11

    relabel_object_ids(root)
    texts_after, attributes_after = _object_ids(root)
    serialized = ET.tostring(root, encoding="unicode")
    assert not any(old in serialized for old in originals)
    assert len(set(texts_after) | set(attributes_after)) == len(originals)

    def text_id(xpath):
        return root.find(xpath, NS).text.strip()

    def node_id(name):
        return root.find(f".//p:ProjectStructure//p:Object[@Name='{name}']", NS).get("ObjectId")

    assert text_id(".//p:dataType[@name='ST_Drive']/p:addData/p:data/p:ObjectId") == node_id("ST_Drive")
    assert root.find(".//p:Method[@name='M_Start']", NS).get("ObjectId") == node_id("M_Start")
    assert node_id("ST_Drive") != node_id("M_Start")


# --------------------------------------------------------------------------- #
# Commit 3: STRUCT and ENUM data types
# --------------------------------------------------------------------------- #


def test_sample05_enum(drive_oop):
    assert [(d.name, d.kind) for d in drive_oop.data_types] == [
        ("E_DriveState", "enum"), ("ST_Drive", "struct"),
    ]
    enum = drive_oop.data_types[0]
    assert enum.values == [EnumValue("IDLE", "0"), EnumValue("RUNNING", "10"), EnumValue("FAULT", "99")]
    assert enum.base_type is None  # CODESYS does not export ") INT;"
    base = ET.fromstring(enum.base_type_xml)
    assert base.tag == PREFIX + "baseType" and base[0].tag == PREFIX + "enum"
    assert enum.attributes == [Attribute("qualified_only", ""), Attribute("strict", "")]
    assert enum.members == []
    assert enum.vendor_xml == []
    assert enum.comment == ""
    assert (enum.configuration, enum.application) == OWNER
    assert drive_oop.warnings == []


def test_sample05_struct(drive_oop):
    struct = drive_oop.data_types[1]
    assert [(v.name, v.type, v.initial_value, v.derived_types) for v in struct.members] == [
        ("sName", "STRING(20)", None, []),
        ("rSpeedSet", "REAL", "0.0", []),
        ("aCurrent", "ARRAY[1..3] OF REAL", None, []),
        ("eState", "E_DriveState", "E_DriveState.IDLE", ["E_DriveState"]),
    ]
    assert {(v.scope, v.section, v.configuration, v.application) for v in struct.members} == {
        ("ST_Drive", "struct", *OWNER),
    }
    assert struct.values == [] and struct.attributes == [] and struct.base_type is None
    assert struct.vendor_xml == []
    assert "ST_Drive" not in {v.scope for v in drive_oop.all_variables()}


DATA_TYPE_CASES = [
    (ENUM + "//p:value[@name='RUNNING']", "value", "11", lambda p: p.data_types[0].values),
    (ENUM + "//p:Attribute[@Name='strict']", "Value", "x", lambda p: p.data_types[0].attributes),
    (STRUCT + "//p:variable[@name='sName']/p:type/p:string", "length", "40",
     lambda p: p.data_types[1].members[0].type),
]


@pytest.mark.parametrize(
    "xpath,attribute,value,field", DATA_TYPE_CASES,
    ids=[f"{attribute}={value}" for _, attribute, value, _ in DATA_TYPE_CASES],
)
def test_sample05_data_types_lossless(xpath, attribute, value, field):
    original = ET.parse(DRIVE_OOP).getroot()
    changed = deepcopy(original)
    changed.find(xpath, NS).set(attribute, value)
    before, after = parse_element(original), parse_element(changed)
    assert field(before) != field(after)
    assert before != after


@pytest.mark.parametrize("parent,fragment", [
    (ENUM + "/p:addData", '<data xmlns="{ns}" name="urn:vendor" mode="a"/>'),
    (ENUM, '<Extra xmlns="{ns}" mode="a"/>'),
], ids=["unmodelled-addData", "unexpected-child"])
def test_data_type_residual_xml(parent, fragment):
    """SYNTHETIC: unknown vendor content on a DUT is kept in vendor_xml, and only there."""
    root = ET.parse(DRIVE_OOP).getroot()
    extra = ET.fromstring(fragment.format(ns=NS["p"]))
    root.find(parent, NS).append(extra)
    first = parse_element(root)
    extra.set("mode", "b")
    second = parse_element(root)
    assert len(first.data_types[0].vendor_xml) == 1 and 'mode="a"' in first.data_types[0].vendor_xml[0]
    assert first.data_types[0].vendor_xml != second.data_types[0].vendor_xml
    assert first.data_types[0].attributes == second.data_types[0].attributes
    assert first.warnings == []


def test_data_type_object_ids_are_noise():
    root = ET.parse(DRIVE_OOP).getroot()
    before = parse_element(root)
    assert parse_element(relabel_object_ids(root)) == before


def test_synthetic_data_type_in_standard_location():
    """SYNTHETIC: types/dataTypes is empty in CODESYS exports, and enum/baseType is never written."""
    root = ET.parse(DRIVE_OOP).getroot()
    enum = deepcopy(root.find(ENUM, NS))
    enum.set("name", "E_Project")
    ET.SubElement(enum.find(".//p:enum", NS), PREFIX + "baseType").append(ET.Element(PREFIX + "INT"))
    root.find("./p:types/p:dataTypes", NS).append(enum)
    project = parse_element(root)
    assert [(d.name, d.configuration, d.application) for d in project.data_types] == [
        ("E_Project", None, None), ("E_DriveState", *OWNER), ("ST_Drive", *OWNER),
    ]
    assert project.data_types[0].base_type == "INT"
    assert project.data_types[1].base_type is None
    assert project.warnings == []


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_data_types_follow_pou_rule(conflicting):
    root = ET.parse(DRIVE_OOP).getroot()
    resource_data = root.find(".//p:resource/p:addData", NS)
    duplicate = deepcopy(resource_data[0])  # the E_DriveState wrapper
    if conflicting:
        duplicate.find(".//p:value[@name='FAULT']", NS).set("value", "98")
    resource_data.append(duplicate)
    project = parse_element(root)
    assert [d.name for d in project.data_types] == (
        ["E_DriveState", "ST_Drive", "E_DriveState"] if conflicting else ["E_DriveState", "ST_Drive"]
    )
    expected = "conflicting definition retained" if conflicting else "identical definition ignored"
    assert project.warnings == [f"duplicate data type 'E_DriveState' in 'Device'/'Application': {expected}"]
