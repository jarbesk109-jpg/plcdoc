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
    structure_before = parse_element(root).structure
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
    assert parse_element(root).structure == structure_before  # joins still resolve


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


# --------------------------------------------------------------------------- #
# Commit 4: methods, actions, properties
# --------------------------------------------------------------------------- #

FB = ".//p:pou[@name='FB_Drive']"
METHOD = FB + "//p:Method[@name='M_Start']"
PROPERTY = FB + "//p:Property[@name='P_Speed']"
M_START_BODY = (
    "xOk := rTarget >= 0.0;\n"
    "IF xOk THEN\n"
    "    stData.rSpeedSet := rTarget;\n"
    "    stData.eState := E_DriveState.RUNNING;\n"
    "END_IF\n"
    "M_Start := xOk;"
)


def _pou(project, name):
    return next(p for p in project.pous if p.name == name)


def test_sample05_fb_drive_members(drive_oop):
    fb = _pou(drive_oop, "FB_Drive")
    assert [m.name for m in fb.methods] == ["M_Start"]
    method = fb.methods[0]
    assert method.return_type == "BOOL"
    assert [(v.name, v.type, v.section, v.scope) for v in method.variables] == [
        ("rTarget", "REAL", "input", "FB_Drive.M_Start"),
        ("xOk", "BOOL", "local", "FB_Drive.M_Start"),
    ]
    assert method.body_language == "ST" and method.body_text == M_START_BODY
    assert method.vendor_xml == [] and method.interface_vendor_xml == []

    assert [a.name for a in fb.actions] == ["A_Reset"]
    assert fb.actions[0].body_text == "stData.eState := E_DriveState.IDLE;\nstData.rSpeedSet := 0.0;"
    assert fb.actions[0].vendor_xml == []

    assert [p.name for p in fb.properties] == ["P_Speed"]
    prop = fb.properties[0]
    assert prop.type == "REAL"
    assert (prop.getter.kind, prop.setter.kind) == ("Get", "Set")
    assert prop.setter.body_text == "rSpeed := P_Speed;"
    assert prop.getter.body_text == " P_Speed := rSpeed;"  # leading space typed in the editor
    assert prop.getter.variables == [] and prop.setter.variables == []
    assert len(prop.interface_vendor_xml) == 1 and "AccessModifiers" in prop.interface_vendor_xml[0]
    assert prop.vendor_xml == []

    assert fb.vendor_xml == [] and fb.interface_vendor_xml == []
    prg = _pou(drive_oop, "PLC_PRG")
    assert (prg.methods, prg.actions, prg.properties) == ([], [], [])
    assert drive_oop.warnings == []


def test_sample05_all_variables_includes_member_scopes(drive_oop):
    P, F, M = "PLC_PRG", "FB_Drive", "FB_Drive.M_Start"
    names = [(v.scope, v.name) for v in drive_oop.all_variables()]
    assert names == [
        (P, "fbDrive"), (P, "xStart"), (P, "xOk"), (P, "rActual"),
        (F, "xEnable"), (F, "xRunning"), (F, "stData"), (F, "rSpeed"),
        (M, "rTarget"), (M, "xOk"),
    ]
    assert len({v.identity for v in drive_oop.all_variables()}) == 10


def _declare(interface, name, type_tag="BOOL", section="localVars", **attrs):
    section_elem = interface.find("p:" + section, NS)
    if section_elem is None:
        section_elem = ET.SubElement(interface, PREFIX + section)
    var = ET.SubElement(section_elem, PREFIX + "variable", name=name, **attrs)
    ET.SubElement(ET.SubElement(var, PREFIX + "type"), PREFIX + type_tag)
    return var


@pytest.mark.parametrize("swapped", [False, True])
def test_accessor_variables_are_get_then_set(swapped):
    """SYNTHETIC: accessor variables follow the model order Get, Set, not the XML order."""
    root = ET.parse(DRIVE_OOP).getroot()
    prop = root.find(PROPERTY, NS)
    _declare(prop.find("p:GetAccessor/p:interface", NS), "xG")
    _declare(prop.find("p:SetAccessor/p:interface", NS), "xS")
    if swapped:
        setter = prop.find("p:SetAccessor", NS)
        prop.remove(setter)
        prop.insert(list(prop).index(prop.find("p:GetAccessor", NS)) + 1, setter)
    project = parse_element(root)
    assert [(v.scope, v.name) for v in project.all_variables()][-2:] == [
        ("FB_Drive.P_Speed.Get", "xG"), ("FB_Drive.P_Speed.Set", "xS"),
    ]
    assert project.warnings == []


def test_addressed_method_variable_enters_io_table():
    """SYNTHETIC: Decision 012 consequence — io_table() sees method variables."""
    from plcdoc.tables import io_table

    root = ET.parse(DRIVE_OOP).getroot()
    root.find(METHOD + "//p:variable[@name='rTarget']", NS).set("address", "%IW9")
    rows = io_table(parse_element(root))
    assert [(r.address, r.direction, r.name, r.type, r.scope) for r in rows] == [
        ("%IW9", "input", "rTarget", "REAL", "FB_Drive.M_Start"),
    ]


MEMBER_CASES = [
    (METHOD + "/p:interface/p:returnType/p:BOOL", "tag", PREFIX + "INT",
     lambda p: _pou(p, "FB_Drive").methods[0].return_type),
    (METHOD + "//p:variable[@name='rTarget']/p:type/p:REAL", "tag", PREFIX + "LREAL",
     lambda p: _pou(p, "FB_Drive").methods[0].variables[0].type),
    (FB + "/p:actions/p:action/p:body/p:ST/{http://www.w3.org/1999/xhtml}xhtml", "text", "x := 1;",
     lambda p: _pou(p, "FB_Drive").actions[0].body_text),
    (PROPERTY + "/p:SetAccessor/p:body/p:ST/{http://www.w3.org/1999/xhtml}xhtml", "text", "rSpeed := 0.0;",
     lambda p: _pou(p, "FB_Drive").properties[0].setter.body_text),
]


@pytest.mark.parametrize(
    "xpath,what,value,field", MEMBER_CASES,
    ids=["method-return-type", "method-variable-type", "action-body", "setter-body"],
)
def test_sample05_members_lossless(xpath, what, value, field):
    original = ET.parse(DRIVE_OOP).getroot()
    changed = deepcopy(original)
    target = changed.find(xpath, NS)
    assert target is not None
    setattr(target, what, value)
    before, after = parse_element(original), parse_element(changed)
    assert field(before) != field(after)
    assert before != after


def _vendor_fields(obj):
    return {name: getattr(obj, name) for name in ("vendor_xml", "interface_vendor_xml") if hasattr(obj, name)}


RESIDUAL_CASES = [
    (FB + "/p:interface", "addData", lambda p: _pou(p, "FB_Drive"), "interface_vendor_xml"),
    (FB + "/p:addData", "data", lambda p: _pou(p, "FB_Drive"), "vendor_xml"),
    (FB, "Transitions", lambda p: _pou(p, "FB_Drive"), "vendor_xml"),
    (METHOD + "/p:addData", "data", lambda p: _pou(p, "FB_Drive").methods[0], "vendor_xml"),
    (METHOD + "/p:interface", "addData", lambda p: _pou(p, "FB_Drive").methods[0], "interface_vendor_xml"),
    (METHOD, "Extra", lambda p: _pou(p, "FB_Drive").methods[0], "vendor_xml"),
    (PROPERTY + "/p:SetAccessor", "Extra", lambda p: _pou(p, "FB_Drive").properties[0].setter, "vendor_xml"),
    (PROPERTY + "/p:SetAccessor/p:interface", "addData",
     lambda p: _pou(p, "FB_Drive").properties[0].setter, "interface_vendor_xml"),
    (FB + "/p:actions/p:action", "Extra", lambda p: _pou(p, "FB_Drive").actions[0], "vendor_xml"),
    (PROPERTY + "/p:addData", "data", lambda p: _pou(p, "FB_Drive").properties[0], "vendor_xml"),
    (PROPERTY + "/p:interface/p:addData/p:data/p:AccessModifiers", "Modifier",
     lambda p: _pou(p, "FB_Drive").properties[0], "interface_vendor_xml"),
]


def _insert(root, parent_xpath, kind, mode):
    """Insert an unknown element at *parent_xpath*; ``kind`` is the shape of the extension."""
    parent = root.find(parent_xpath, NS)
    assert parent is not None, parent_xpath
    if kind == "data":
        ET.SubElement(parent, PREFIX + "data", name="urn:vendor", mode=mode)
    elif kind == "addData":
        holder = ET.SubElement(parent, PREFIX + "addData")
        ET.SubElement(holder, PREFIX + "data", name="urn:vendor", mode=mode)
    else:
        ET.SubElement(parent, PREFIX + kind, mode=mode)


@pytest.mark.parametrize(
    "parent,kind,owner,field", RESIDUAL_CASES,
    ids=[f"{parent.rpartition('/')[2]}+{kind}->{field}" for parent, kind, _, field in RESIDUAL_CASES],
)
def test_residual_xml_is_kept_at_its_location(parent, kind, owner, field):
    """SYNTHETIC: each location's residual content lands in that owner's field, and only there."""
    base = parse_element(ET.parse(DRIVE_OOP).getroot())
    root = ET.parse(DRIVE_OOP).getroot()
    _insert(root, parent, kind, "a")
    first = parse_element(root)
    root = ET.parse(DRIVE_OOP).getroot()
    _insert(root, parent, kind, "b")
    second = parse_element(root)
    for name, value in _vendor_fields(owner(first)).items():
        if name == field:
            assert value != getattr(owner(base), name)
            assert value != getattr(owner(second), name)
            assert any('mode="a"' in entry for entry in value)
        else:
            assert value == getattr(owner(base), name), name
    assert first != base and first != second


def test_moving_an_extension_between_property_locations_changes_the_model():
    at_interface = ET.parse(DRIVE_OOP).getroot()
    _insert(at_interface, PROPERTY + "/p:interface/p:addData", "data", "a")
    at_property = ET.parse(DRIVE_OOP).getroot()
    _insert(at_property, PROPERTY + "/p:addData", "data", "a")
    first, second = parse_element(at_interface), parse_element(at_property)
    assert first != second
    prop_first, prop_second = _pou(first, "FB_Drive").properties[0], _pou(second, "FB_Drive").properties[0]
    assert prop_first.interface_vendor_xml != prop_second.interface_vendor_xml
    assert prop_first.vendor_xml != prop_second.vendor_xml
    assert prop_first.getter == prop_second.getter and prop_first.setter == prop_second.setter


def test_residual_fragment_strips_nested_object_ids_only():
    """SYNTHETIC: a GUID inside a preserved subtree is noise; everything else in it counts."""
    root = ET.parse(DRIVE_OOP).getroot()
    extra = ET.SubElement(root.find(METHOD, NS), PREFIX + "Extra", mode="a")
    add_data = ET.SubElement(extra, PREFIX + "addData")
    object_id = ET.SubElement(
        ET.SubElement(add_data, PREFIX + "data", name="http://www.3s-software.com/plcopenxml/objectid"),
        PREFIX + "ObjectId",
    )
    object_id.text = "11111111-1111-1111-1111-111111111111"
    vendor = ET.SubElement(add_data, PREFIX + "data", name="urn:vendor", k="1")
    before = parse_element(root)
    fragment = _pou(before, "FB_Drive").methods[0].vendor_xml
    assert len(fragment) == 1 and "urn:vendor" in fragment[0] and "ObjectId" not in fragment[0]

    object_id.text = "22222222-2222-2222-2222-222222222222"
    assert parse_element(root) == before
    vendor.set("k", "2")
    assert _pou(parse_element(root), "FB_Drive").methods[0].vendor_xml != fragment
    vendor.set("k", "1")
    extra.set("mode", "b")
    assert _pou(parse_element(root), "FB_Drive").methods[0].vendor_xml != fragment


def test_accessor_order_does_not_matter():
    root = ET.parse(DRIVE_OOP).getroot()
    before = parse_element(root)
    prop = root.find(PROPERTY, NS)
    setter = prop.find("p:SetAccessor", NS)
    prop.remove(setter)
    prop.insert(list(prop).index(prop.find("p:GetAccessor", NS)) + 1, setter)
    assert parse_element(root) == before


def test_member_object_ids_are_noise():
    root = ET.parse(DRIVE_OOP).getroot()
    before = parse_element(root)
    assert parse_element(relabel_object_ids(root)) == before


# --------------------------------------------------------------------------- #
# Commit 5: ProjectStructure joined by ObjectId
# --------------------------------------------------------------------------- #


def _tree(nodes):
    return [(n.name, n.kind, _tree(n.children)) for n in nodes]


def test_sample05_structure(drive_oop):
    assert _tree(drive_oop.structure) == [
        ("Device", "configuration", [
            ("Application", "application", [
                ("Library Manager", "libraries", []),
                ("PLC_PRG", "pou", []),
                ("MainTask", "task", []),
                ("E_DriveState", "datatype", []),
                ("ST_Drive", "datatype", []),
                ("FB_Drive", "pou", [
                    ("M_Start", "method", []),
                    ("A_Reset", "action", []),
                    ("P_Speed", "property", []),
                ]),
            ]),
        ]),
    ]


def test_sample03_structure_has_gvl_kind(large):
    application = large.structure[0].children[0]
    kinds = {node.name: node.kind for node in application.children}
    assert kinds["GVL_IO"] == "gvl"
    assert kinds["PRG_Alarm"] == "pou"
    assert None not in kinds.values()


def test_structure_unknown_object_is_a_folder():
    """SYNTHETIC: a folder has an ObjectId that matches no exported object; no warning."""
    root = ET.parse(DRIVE_OOP).getroot()
    application = root.find(".//p:ProjectStructure/p:Object/p:Object", NS)
    prg = application.find("p:Object[@Name='PLC_PRG']", NS)
    application.remove(prg)
    folder = ET.SubElement(application, PREFIX + "Object", Name="Folder", ObjectId="f01de000-0000-4000-8000-000000000001")
    folder.append(prg)
    project = parse_element(root)
    folder_node = next(n for n in project.structure[0].children[0].children if n.name == "Folder")
    assert folder_node.kind is None
    assert _tree(folder_node.children) == [("PLC_PRG", "pou", [])]
    assert project.warnings == []


@pytest.mark.parametrize("xpath,attribute,node_name", [
    (STRUCT + "/p:addData/p:data/p:ObjectId", None, "ST_Drive"),
    (METHOD, "ObjectId", "M_Start"),
], ids=["datatype-text-id", "method-attribute-id"])
def test_broken_join_changes_kind(xpath, attribute, node_name):
    """Changing only the declaration's GUID (not the structure's) breaks that one join."""
    root = ET.parse(DRIVE_OOP).getroot()
    before = parse_element(root)
    target = root.find(xpath, NS)
    if attribute is None:
        target.text = "deadbeef-0000-4000-8000-000000000000"
    else:
        target.set(attribute, "deadbeef-0000-4000-8000-000000000000")
    after = parse_element(root)
    assert after != before

    def find(nodes):
        for node in nodes:
            if node.name == node_name:
                return node
            found = find(node.children)
            if found is not None:
                return found
        return None

    assert find(before.structure).kind is not None
    assert find(after.structure).kind is None
