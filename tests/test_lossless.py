"""M2.1 regression probes: semantic edits must survive the XML/model boundary.

Mutate copies of real exports; synthetic fragments cover shapes absent from the
samples (nested arrays, WSTRING, struct values and generic graphical extensions).
"""

from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from plcdoc import PouInstance, parse_file
from plcdoc.parser import parse_element

from conftest import LARGE, TYPES_QUALIFIERS

NS = {"p": "http://www.plcopen.org/xml/tc6_0200"}
PREFIX = "{" + NS["p"] + "}"
PRG = ".//p:pou[@name='PLC_PRG']"
LOCAL = PRG + "/p:interface/p:localVars"
SETPOINTS = LOCAL + "/p:variable[@name='aSetpoints']"
SPARE = LOCAL + "/p:variable[@name='aSpare']"
EXTRA = ".//p:resource/p:globalVars[@name='GVL_Extra']"
MIXED = EXTRA + "/p:addData/p:data/p:MixedAttrsVarList"


def _payload(project):
    result = project.to_dict()
    result.pop("warnings")  # A warning is NOT evidence that the changed data survived.
    return result


@pytest.mark.parametrize("xpath,attribute,value", [
    (".//p:LD/p:contact/p:variable", None, "bEStopOK"),
    (".//p:LD/p:coil/p:variable", None, "bLampAlarm"),
    (".//p:LD/p:contact", "negated", "false"),
    (".//p:LD/p:coil", "negated", "true"),
    (".//p:LD/p:coil", "storage", "set"),
    (".//p:LD/p:contact", "edge", "rising"),
    (".//p:LD/p:contact", "localId", "30"),
    (".//p:LD/p:coil/p:connectionPointIn/p:connection", "refLocalId", "0"),
    (".//p:task/p:pouInstance", "name", "MainInstance"),
    (".//p:task/p:pouInstance", "typeName", "PRG_Alarm"),
    (".//p:configuration", "name", "Device2"),
    (".//p:resource", "name", "Application2"),
    (LOCAL, "retain", "true"),
    (LOCAL, "nonretain", "true"),
    (LOCAL, "persistent", "true"),
    (LOCAL, "constant", "true"),
    (MIXED + "/p:globalVars[@retain='true']", "retain", "false"),
    (MIXED + "/p:globalVars[@constant='true']", "constant", "false"),
    (SETPOINTS + "/p:type/p:array/p:dimension", "lower", "0"),
    (SETPOINTS + "/p:type/p:array/p:dimension", "upper", "8"),
    (SPARE + "/p:type/p:array/p:baseType/p:derived", "name", "OtherMotor"),
    (EXTRA + "/p:variable[@name='sRecipeName']/p:type/p:string", "length", "80"),
    (SETPOINTS + "/p:initialValue/p:arrayValue/p:value/p:simpleValue", "value", "100"),
    (SETPOINTS + "/p:initialValue/p:arrayValue/p:value", "repetitionValue", "2"),
    (SPARE + "/p:type/p:array", "vendorAttribute", "preserve me"),
    (".//p:pou[@name='FC_Scale']/p:interface/p:returnType/p:REAL", "vendorAttribute", "v2"),
], ids=lambda value: str(value))
def test_lossless(xpath, attribute, value):
    original = ET.parse(TYPES_QUALIFIERS).getroot()
    changed = deepcopy(original)
    target = changed.find(xpath, NS)
    assert target is not None
    if attribute is None:
        target.text = value
    else:
        target.set(attribute, value)
    assert _payload(parse_element(changed)) != _payload(parse_element(original))


@pytest.mark.parametrize("element_name", ["BOOL", "REAL"])
def test_lossless_array_element_type(element_name):
    root = ET.parse(TYPES_QUALIFIERS).getroot()
    before = parse_element(root)
    root.find(SETPOINTS + "/p:type/p:array/p:baseType/p:INT", NS).tag = PREFIX + element_name
    after = parse_element(root)
    assert _payload(before) != _payload(after)
    assert next(v for v in after.pous[0].variables if v.name == "aSetpoints").type.endswith(element_name)


def _type_variant(type_content, initial_content=None):
    root = ET.parse(TYPES_QUALIFIERS).getroot()
    var = root.find(SETPOINTS, NS)
    var.remove(var.find("p:type", NS))
    var.insert(0, ET.fromstring(f'<type xmlns="{NS["p"]}">{type_content}</type>'))
    var.remove(var.find("p:initialValue", NS))
    if initial_content is not None:
        var.append(ET.fromstring(f'<initialValue xmlns="{NS["p"]}">{initial_content}</initialValue>'))
    project = parse_element(root)
    return next(v for v in project.pous[0].variables if v.name == "aSetpoints")


@pytest.mark.parametrize("xml,expected,derived", [
    ('<array><dimension lower="-1" upper="2"/><dimension lower="0" upper="3"/>'
     '<baseType><REAL/></baseType></array>', "ARRAY[-1..2, 0..3] OF REAL", []),
    ('<array><dimension lower="1" upper="2"/><baseType><array>'
     '<dimension lower="3" upper="4"/><baseType><derived name="FB_Motor"/>'
     '</baseType></array></baseType></array>',
     "ARRAY[1..2] OF ARRAY[3..4] OF FB_Motor", ["FB_Motor"]),
    ('<string length="40"/>', "STRING(40)", []),
    ('<wstring length="40"/>', "WSTRING(40)", []),
    ('<string/>', "STRING", []),
    ('<wstring/>', "WSTRING", []),
])
def test_recursive_types(xml, expected, derived):
    var = _type_variant(xml)
    assert var.type == expected
    assert var.derived_types == derived
    assert var.is_derived == bool(derived)


@pytest.mark.parametrize("before,after", [
    ('<struct><variable name="a"><type><INT/></type></variable></struct>',
     '<struct><variable name="b"><type><INT/></type></variable></struct>'),
    ('<subrangeSigned><range lower="0" upper="10"/><baseType><INT/></baseType></subrangeSigned>',
     '<subrangeSigned><range lower="0" upper="20"/><baseType><INT/></baseType></subrangeSigned>'),
    ('<vendorType mode="a"><nested>one</nested></vendorType>',
     '<vendorType mode="a"><nested>two</nested></vendorType>'),
    ('<vendorType xmlns="urn:vendor:a"/>', '<vendorType xmlns="urn:vendor:b"/>'),
    ('<wstring length="20"/>', '<wstring length="21"/>'),
    ('<derived name="INT"/>', '<INT/>'),
])
def test_lossless_type_fallback(before, after):
    first, second = _type_variant(before), _type_variant(after)
    assert first != second
    assert first.type_xml != second.type_xml
    assert ET.fromstring(first.type_xml).tag == PREFIX + "type"


@pytest.mark.parametrize("before,after", [
    ('<arrayValue><value><simpleValue value="10"/></value></arrayValue>',
     '<arrayValue><value><simpleValue value="20"/></value></arrayValue>'),
    ('<arrayValue><value repetitionValue="2"><simpleValue value="10"/></value></arrayValue>',
     '<arrayValue><value repetitionValue="3"><simpleValue value="10"/></value></arrayValue>'),
    ('<structValue><value member="a"><simpleValue value="1"/></value></structValue>',
     '<structValue><value member="b"><simpleValue value="1"/></value></structValue>'),
    ('<structValue><value member="a"><simpleValue value="1"/></value></structValue>',
     '<structValue><value member="a"><simpleValue value="2"/></value></structValue>'),
    ('<vendorValue><nested value="1"/></vendorValue>',
     '<vendorValue><nested value="2"/></vendorValue>'),
    (None, ""),
    ('<simpleValue value=" "/>', '<simpleValue value=""/>'),
])
def test_lossless_initial_values(before, after):
    first, second = _type_variant("<INT/>", before), _type_variant("<INT/>", after)
    assert first.initial_value != second.initial_value
    assert first.initial_value_xml != second.initial_value_xml


@pytest.mark.parametrize("language", ["FBD", "CFC"])
def test_generic_graphical_fallback_preserves_block_details(language):
    root = ET.parse(LARGE).getroot()
    body = root.find(PRG + "/p:body", NS)
    body.clear()
    body.append(ET.fromstring(
        f'<{language} xmlns="{NS["p"]}"><block localId="7" typeName="FB_Motor" instanceName="fbConv1">'
        '<inputVariables><variable formalParameter="bStart"><connectionPointIn>'
        '<connection refLocalId="3" formalParameter="Q"/></connectionPointIn></variable></inputVariables>'
        '<vendorSettings xmlns="urn:vendor" mode="first"/>'
        f'</block></{language}>'
    ))
    before = parse_element(root)
    block = before.pous[0].graphical_body[0]
    assert (block.kind, block.local_id, block.incoming_ref_local_ids) == ("block", "7", ["3"])
    assert 'typeName="FB_Motor"' in block.xml and 'formalParameter="bStart"' in block.xml
    assert ET.fromstring(before.pous[0].body_xml).tag == PREFIX + language
    root.find(".//{urn:vendor}vendorSettings").set("mode", "second")
    after = parse_element(root)
    assert before.pous[0].graphical_body != after.pous[0].graphical_body
    assert before.pous[0].body_xml != after.pous[0].body_xml


@pytest.mark.parametrize("owner_kind", ["application", "configuration"])
def test_distinct_owners_preserve_same_named_objects(owner_kind):
    root = ET.parse(LARGE).getroot()
    if owner_kind == "application":
        parent = root.find(".//p:configuration", NS)
        other = deepcopy(parent.find("p:resource", NS))
        other.set("name", "Application2")
    else:
        parent = root.find("./p:instances/p:configurations", NS)
        other = deepcopy(parent.find("p:configuration", NS))
        other.set("name", "Device2")
    parent.append(other)
    project = parse_element(root)
    assert (len(project.pous), len(project.gvls), len(project.tasks)) == (8, 2, 2)
    assert len(list(project.all_variables())) == 72
    assert len({(v.configuration, v.identity) for v in project.all_variables()}) == 72
    assert project.warnings == []
    for owner in [*project.pous, *project.gvls]:
        assert all((v.configuration, v.application) == (owner.configuration, owner.application)
                   for v in owner.variables)
    assert {(t.configuration, t.application) for t in project.tasks} == {
        (g.configuration, g.application) for g in project.gvls
    }


@pytest.mark.parametrize("conflicting", [False, True])
def test_only_identical_pous_in_same_resource_are_deduplicated(conflicting):
    root = ET.parse(LARGE).getroot()
    data = root.find(".//p:resource/p:addData", NS)
    duplicate = deepcopy(data[0])
    if conflicting:
        duplicate.find(".//{http://www.w3.org/1999/xhtml}xhtml").text = "different comment"
    data.append(duplicate)
    project = parse_element(root)
    assert len(project.pous) == (5 if conflicting else 4)
    assert len(project.warnings) == 1
    assert ("conflicting definition retained" if conflicting else "identical definition ignored") in project.warnings[0]


def test_task_instance_name_and_type_are_independent():
    root = ET.parse(LARGE).getroot()
    instance = root.find(".//p:task/p:pouInstance", NS)
    instance.set("name", "MainInstance")
    instance.set("typeName", "PLC_PRG")
    assert parse_element(root).tasks[0].programs == [PouInstance("MainInstance", "PLC_PRG")]


def test_canonical_data_ignores_prefix_attribute_order_and_indentation():
    plain = _type_variant(
        '<vendorType z="2" a="1"><nested value="3"/></vendorType>',
        '<structValue><value member="x"><simpleValue value="5"/></value></structValue>',
    )
    formatted = _type_variant(
        f'<p:vendorType xmlns:p="{NS["p"]}" a="1" z="2">\n'
        '  <p:nested value="3"/>\n</p:vendorType>',
        '<structValue>\n <value member="x">\n <simpleValue value="5"/>\n </value>\n</structValue>',
    )
    assert plain == formatted


@pytest.mark.parametrize("before,after", [
    ('<vendorType>left<part/> </vendorType>', '<vendorType>left<part/></vendorType>'),
    ('<vendorType xml:space="preserve"> <part/> </vendorType>',
     '<vendorType xml:space="preserve"><part/></vendorType>'),
    ('<vendorType> </vendorType>', '<vendorType/>'),
])
def test_canonical_fallback_preserves_significant_whitespace(before, after):
    assert _type_variant(before) != _type_variant(after)


@pytest.mark.parametrize("kind", ["position", "relPosition", "comment", "vendorElement"])
def test_graphical_fallback_does_not_filter_vendor_namesakes(kind):
    root = ET.parse(LARGE).getroot()
    ld = root.find(".//p:LD", NS)
    extension = ET.SubElement(ld, "{urn:vendor}" + kind, mode="first")
    before = parse_element(root)
    extension.set("mode", "second")
    assert _payload(before) != _payload(parse_element(root))


def test_parse_element_is_pure_and_ignores_documented_noise():
    root = ET.parse(LARGE).getroot()
    xml_before = ET.tostring(root)
    before = parse_element(root)
    assert ET.tostring(root) == xml_before
    for position in root.findall(".//p:LD//p:position", NS):
        position.set("x", "99")
    for obj in root.iter(PREFIX + "ObjectId"):
        obj.text = "another-guid"
    root.find("p:fileHeader", NS).set("creationDateTime", "2020-01-01T00:00:00")
    root.find("p:contentHeader", NS).set("modificationDateTime", "2020-01-01T00:00:00")
    assert parse_element(root) == before
    assert parse_file(LARGE) == before
