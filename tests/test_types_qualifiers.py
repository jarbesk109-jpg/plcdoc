"""The real fourth export: mixed CODESYS qualifiers and the 03 -> 04 diff pair."""

from copy import deepcopy
from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest

from plcdoc.parser import parse_element
from plcdoc.tables import io_table

from conftest import LARGE, TYPES_QUALIFIERS

NS = {"p": "http://www.plcopen.org/xml/tc6_0200"}
QUALIFIERS = ("retain", "nonretain", "persistent", "constant")


def test_sample04_types_and_qualifiers(types_qualifiers):
    project = types_qualifiers
    assert project.warnings == []
    assert len(project.pous) == 4
    assert [g.name for g in project.gvls] == ["GVL_IO", "GVL_Extra"]
    assert [len(g.variables) for g in project.gvls] == [22, 4]
    assert len(list(project.all_variables())) == 42
    assert len(io_table(project)) == 20
    assert {(r.configuration, r.application) for r in io_table(project)} == {("Device", "Application")}

    extra = {v.name: v for v in project.gvls[1].variables}
    assert {name: v.type for name, v in extra.items()} == {
        "aTemps": "ARRAY[1..4] OF REAL", "sRecipeName": "STRING(20)",
        "diTotalCount": "DINT", "MAX_ZONES": "INT",
    }
    assert extra["MAX_ZONES"].initial_value == "4"
    assert {name: tuple(getattr(v, q) for q in QUALIFIERS) for name, v in extra.items()} == {
        "aTemps": (False, False, False, False),
        "sRecipeName": (False, False, False, False),
        "diTotalCount": (True, False, False, False),
        "MAX_ZONES": (False, False, False, True),
    }
    assert all(not any(getattr(v, q) for q in QUALIFIERS) for v in project.gvls[0].variables)
    for owner in [*project.pous, *project.gvls, *project.tasks]:
        assert (owner.configuration, owner.application) == ("Device", "Application")
    assert all(
        v.identity == ("Device", "Application", v.scope, v.name) for v in project.all_variables()
    )


def test_sample04_array_initializers_and_fb_bases(types_qualifiers):
    variables = {v.name: v for v in types_qualifiers.pous[0].variables}
    setpoints = variables["aSetpoints"]
    assert setpoints.type == "ARRAY[1..3] OF INT"
    assert setpoints.derived_types == []
    assert setpoints.initial_value == "(array)"
    init = ET.fromstring(setpoints.initial_value_xml)
    assert [v.attrib["value"] for v in init.findall("p:arrayValue/p:value/p:simpleValue", NS)] == ["10", "20", "30"]
    spare = variables["aSpare"]
    assert spare.type == "ARRAY[1..2] OF FB_Motor"
    assert spare.derived_types == ["FB_Motor"]
    assert spare.initial_value is None
    assert spare.initial_value_xml is None


def test_sample03_to_04_has_exactly_the_documented_additions(large, types_qualifiers):
    """Parser-level ground truth for the second diff pair; M4 owns diff output."""
    before, after = large, types_qualifiers
    assert after.gvls[0] == before.gvls[0]
    assert [g.name for g in after.gvls[1:]] == ["GVL_Extra"]
    assert [v.name for v in after.pous[0].variables[4:]] == ["aSetpoints", "aSpare"]
    assert replace(after.pous[0], variables=after.pous[0].variables[:4]) == before.pous[0]
    assert after.pous[1:] == before.pous[1:]
    assert after.tasks == before.tasks
    original_variables = {v.identity: v for v in before.all_variables()}
    new_variables = {v.identity: v for v in after.all_variables()}
    assert original_variables.keys() <= new_variables.keys()
    assert all(new_variables[key] == var for key, var in original_variables.items())
    assert new_variables.keys() - original_variables.keys() == {
        ("Device", "Application", "GVL_Extra", name)
        for name in ("aTemps", "sRecipeName", "diTotalCount", "MAX_ZONES")
    } | {("Device", "Application", "PLC_PRG", name) for name in ("aSetpoints", "aSpare")}


def test_mixed_blocks_supply_only_qualifiers():
    root = ET.parse(TYPES_QUALIFIERS).getroot()
    extra = root.find(".//p:resource/p:globalVars[@name='GVL_Extra']", NS)
    # Stale nested declarations must not replace the authoritative top-level data.
    retained = extra.find("p:addData/p:data/p:MixedAttrsVarList/p:globalVars[@retain='true']", NS)
    retained.find("p:variable/p:type/p:DINT", NS).tag = "{" + NS["p"] + "}BOOL"
    retained.append(deepcopy(retained.find("p:variable", NS)))
    retained[-1].set("name", "nestedOnly")
    project = parse_element(root)
    assert len(project.gvls) == 2
    variables = {v.name: v for v in project.gvls[1].variables}
    assert len(variables) == 4 and "nestedOnly" not in variables
    assert variables["diTotalCount"].type == "DINT" and variables["diTotalCount"].retain


@pytest.mark.parametrize("qualifier,value", [("persistent", "1"), ("nonretain", "0")])
def test_direct_section_qualifiers_apply_to_every_variable(qualifier, value):
    """Sample 04 already covers retain/constant via MixedAttrsVarList."""
    root = ET.parse(LARGE).getroot()
    gvl = root.find(".//p:resource/p:globalVars", NS)
    gvl.set(qualifier, value)
    project = parse_element(root)
    assert all(getattr(v, qualifier) == (value in ("true", "1")) for v in project.gvls[0].variables)
    assert all(not getattr(v, qualifier) for pou in project.pous for v in pou.variables)


def test_configuration_level_globalvars_ownership():
    root = ET.parse(LARGE).getroot()
    config = root.find(".//p:configuration", NS)
    resource = config.find("p:resource", NS)
    gvl = resource.find("p:globalVars", NS)
    resource.remove(gvl)
    config.insert(1, gvl)
    project = parse_element(root)
    assert len(project.gvls) == 1
    gvl_model = project.gvls[0]
    assert (gvl_model.configuration, gvl_model.application) == ("Device", None)
    assert len(gvl_model.variables) == 22
    assert all((v.configuration, v.application, v.scope) == ("Device", None, "GVL_IO")
               for v in gvl_model.variables)


def test_pou_interface_globalvars_are_not_project_gvls():
    root = ET.parse(LARGE).getroot()
    gvl = root.find(".//p:resource/p:globalVars", NS)
    section = ET.Element("{" + NS["p"] + "}globalVars", retain="true")
    section.append(deepcopy(gvl.find("p:variable", NS)))
    root.find(".//p:pou[@name='PLC_PRG']/p:interface", NS).append(section)
    project = parse_element(root)
    assert [g.name for g in project.gvls] == ["GVL_IO"]
    assert len(project.gvls[0].variables) == 22
    variable = project.pous[0].variables[-1]
    assert (variable.name, variable.scope, variable.section) == ("bStart1", "PLC_PRG", "global")
    assert (variable.configuration, variable.application, variable.retain) == ("Device", "Application", True)
