"""Sample 05 (ENUM, STRUCT, FB method/action/property) and the M3a parser changes.

Facts are checked against ``samples/05_drive_oop.xml``; shapes no export
contains are SYNTHETIC mutations of a parsed sample, marked as such.
"""

from copy import deepcopy
from xml.etree import ElementTree as ET

from plcdoc.parser import parse_element

from conftest import DRIVE_OOP, LARGE, relabel_object_ids

NS = {"p": "http://www.plcopen.org/xml/tc6_0200"}
PREFIX = "{" + NS["p"] + "}"


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
