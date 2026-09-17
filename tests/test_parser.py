"""Parser facts checked against the real CODESYS exports in samples/."""

import pytest

from plcdoc import ParseError, PouInstance, parse_bytes, parse_file, parse_string
from plcdoc.parser import KNOWN_SECTIONS

from conftest import SMALL_V1


def _by_name(variables):
    return {v.name: v for v in variables}


# --------------------------------------------------------------------------- #
# 01_conveyor_v1.xml (small)
# --------------------------------------------------------------------------- #


def test_small_header(small):
    assert small.name == "conveyor_v1.project"
    assert small.product_version == "CODESYS V3.5 SP22 Patch 3"
    assert small.warnings == []


def test_small_has_one_program_from_resource_adddata(small):
    assert [(p.name, p.pou_type) for p in small.pous] == [("PLC_PRG", "program")]
    assert small.gvls == []


def test_small_variables_are_all_local_to_plc_prg(small):
    variables = small.pous[0].variables
    assert [v.name for v in variables] == [
        "bStart",
        "bStop",
        "bSensor",
        "bReset",
        "bMotor",
        "bLampRun",
        "bLampDone",
        "fbCounter",
        "iCount",
        "iPreset",
    ]
    assert {v.scope for v in variables} == {"PLC_PRG"}
    assert {v.section for v in variables} == {"local"}


def test_small_variable_details(small):
    v = _by_name(small.pous[0].variables)

    assert v["bStart"].address == "%IX0.0"
    assert v["bStart"].type == "BOOL"
    assert v["bStart"].is_derived is False
    assert v["bStart"].comment == "Nút Start (NO)"  # leading space stripped
    assert v["bStart"].initial_value is None

    assert v["bLampDone"].address == "%QX0.2"

    assert v["fbCounter"].type == "CTU"
    assert v["fbCounter"].is_derived is True
    assert v["fbCounter"].address is None
    assert v["fbCounter"].comment == "Internal"  # lossy comment attribution, see xml-structure.md

    assert v["iCount"].type == "INT"
    assert v["iCount"].comment == ""
    assert v["iCount"].initial_value is None

    assert v["iPreset"].initial_value == "10"


def test_small_st_body(small):
    pou = small.pous[0]
    assert pou.body_language == "ST"
    assert pou.return_type is None
    assert "bLampRun := bMotor;" in pou.body_text
    assert "Q => bLampDone" in pou.body_text  # &gt; unescaped by the XML parser
    assert "\r" not in pou.body_text  # CRLF normalised


def test_small_task(small):
    assert len(small.tasks) == 1
    task = small.tasks[0]
    assert task.name == "MainTask"
    assert task.interval == "PT0.02S"
    assert task.priority == 1
    assert task.programs == [PouInstance("PLC_PRG", "PLC_PRG")]
    assert (task.configuration, task.application) == ("Device", "Application")


def test_small_v2_reflects_known_changes(small_v2):
    v = _by_name(small_v2.pous[0].variables)
    assert "bEStop" in v and v["bEStop"].address == "%IX0.4"
    assert "bLampRun" not in v
    assert "bSensorIn" in v and "bSensor" not in v
    assert v["iPreset"].initial_value == "20"
    assert v["bLampDone"].address == "%QX0.3"
    assert v["fbCounter"].comment == "Bộ đếm sản phẩm"


def test_small_v1_v2_preserves_every_st_change(small, small_v2):
    before = small.pous[0].body_text
    after = small_v2.pous[0].body_text
    assert before == (
        "fbCounter(CU := bSensor AND bMotor, RESET := bReset, PV := iPreset,\n"
        "          Q => bLampDone, CV => iCount);\n\n"
        "bMotor   := (bStart OR bMotor) AND bStop AND NOT bLampDone;\n"
        "bLampRun := bMotor;"
    )
    assert after == (
        "fbCounter(CU := bSensorIn AND bMotor, RESET := bReset, PV := iPreset,\n"
        "          Q => bLampDone, CV => iCount);\n\n"
        "bMotor := (bStart OR bMotor) AND bStop AND bEStop AND NOT bLampDone;"
    )


# --------------------------------------------------------------------------- #
# 03_line_large.xml (GVL, FB, function, ladder)
# --------------------------------------------------------------------------- #


def test_large_pous_in_document_order(large):
    assert [(p.name, p.pou_type) for p in large.pous] == [
        ("PLC_PRG", "program"),
        ("FB_Motor", "functionBlock"),
        ("FC_Scale", "function"),
        ("PRG_Alarm", "program"),
    ]
    assert large.warnings == []


def test_large_gvl_io_from_resource_level(large):
    assert [g.name for g in large.gvls] == ["GVL_IO"]
    gvl = large.gvls[0]
    assert len(gvl.variables) == 22
    assert {v.scope for v in gvl.variables} == {"GVL_IO"}
    assert {v.section for v in gvl.variables} == {"global"}

    v = _by_name(gvl.variables)
    assert v["bStart1"].address == "%IX0.0"
    assert v["iTankLevelRaw"].address == "%IW10"
    assert v["iTankLevelRaw"].type == "INT"
    assert v["iSpeedRef"].address == "%QW10"
    assert v["bAutoMode"].address == "%MX0.0"
    assert v["bAutoMode"].direction == "memory"
    assert v["rTankLevel"].address is None
    assert v["rTankLevel"].type == "REAL"
    assert v["rTemp"].comment == "Nhiệt độ (°C)"

    addressed = [x for x in gvl.variables if x.address]
    assert len(addressed) == 20
    assert {x.address[:3] for x in addressed} == {"%IX", "%IW", "%QX", "%QW", "%MX"}


def test_large_fb_motor_sections(large):
    fb = next(p for p in large.pous if p.name == "FB_Motor")
    assert fb.return_type is None
    by_section = {}
    for v in fb.variables:
        by_section.setdefault(v.section, []).append(v.name)
    assert by_section == {
        "input": ["bStart", "bStop", "bFault", "bInterlock"],
        "output": ["bRun", "bAlarm"],
        "local": ["tonFault"],
    }
    ton = _by_name(fb.variables)["tonFault"]
    assert ton.type == "TON"
    assert ton.is_derived is True
    assert ton.scope == "FB_Motor"
    assert fb.body_language == "ST"
    assert "bAlarm := tonFault.Q;" in fb.body_text


def test_large_fc_scale_return_type(large):
    fc = next(p for p in large.pous if p.name == "FC_Scale")
    assert fc.return_type == "REAL"
    assert [(v.name, v.type, v.section) for v in fc.variables] == [
        ("iRaw", "INT", "input"),
        ("rMin", "REAL", "input"),
        ("rMax", "REAL", "input"),
    ]
    assert fc.body_language == "ST"
    assert fc.body_text == "FC_Scale := rMin + (INT_TO_REAL(iRaw) / 27648.0) * (rMax - rMin);"


def test_large_prg_alarm_preserves_ladder_semantics(large):
    prg = next(p for p in large.pous if p.name == "PRG_Alarm")
    assert prg.pou_type == "program"
    assert prg.body_language == "LD"
    assert prg.body_text is None
    assert prg.variables == []
    assert [node.kind for node in prg.graphical_body] == [
        "leftPowerRail", "contact", "coil", "rightPowerRail",
    ]
    contact, coil = prg.graphical_body[1:3]
    assert (contact.local_id, contact.variable, contact.negated, contact.storage, contact.edge) == (
        "3", "bDoorClosed", True, "none", "none",
    )
    assert contact.incoming_ref_local_ids == ["0"]
    assert (coil.local_id, coil.variable, coil.negated, coil.storage) == ("4", "bHorn", False, "none")
    assert coil.incoming_ref_local_ids == ["3"]
    assert "bDoorClosed" in prg.body_xml and "bHorn" in prg.body_xml
    assert "position" not in prg.body_xml and "networktitle" not in prg.body_xml


def test_large_plc_prg_uses_fb_instances(large):
    prg = next(p for p in large.pous if p.name == "PLC_PRG")
    v = _by_name(prg.variables)
    assert v["fbConv1"].type == "FB_Motor"
    assert v["fbConv1"].is_derived is True
    assert v["bLineReady"].type == "BOOL"
    assert "rTankLevel := FC_Scale(iRaw := iTankLevelRaw, rMin := 0.0, rMax := 100.0);" in prg.body_text
    assert "rTemp      := FC_Scale(iRaw := iTempRaw, rMin := -20.0, rMax := 150.0);" in prg.body_text
    assert prg.body_text.endswith("PRG_Alarm();")


def test_large_all_variables_gvl_first_then_pous(large):
    names = [(v.scope, v.name) for v in large.all_variables()]
    assert len(names) == 22 + 4 + 7 + 3
    assert names[0] == ("GVL_IO", "bStart1")
    assert names[22] == ("PLC_PRG", "fbConv1")
    assert len(list(large.io_variables())) == 20


def test_large_task(large):
    assert [(t.name, t.programs) for t in large.tasks] == [
        ("MainTask", [PouInstance("PLC_PRG", "PLC_PRG")]),
    ]


# --------------------------------------------------------------------------- #
# Synthetic inputs: things no sample export contains yet
# --------------------------------------------------------------------------- #

_SYNTHETIC_HEAD = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<project xmlns="http://www.plcopen.org/xml/tc6_0200">'
    '<fileHeader productName="x" productVersion="synthetic" creationDateTime="2026-01-01T00:00:00"/>'
    '<contentHeader name="synthetic.project"/>'
)
_SYNTHETIC_TAIL = "</project>"


def _pou(name, section="localVars", var="x", address=None):
    addr = f' address="{address}"' if address else ""
    return (
        f'<pou name="{name}" pouType="program"><interface><{section}>'
        f'<variable name="{var}"{addr}><type><BOOL/></type></variable>'
        f"</{section}></interface><body><ST>"
        '<xhtml xmlns="http://www.w3.org/1999/xhtml">x := TRUE;</xhtml>'
        "</ST></body></pou>"
    )


def test_synthetic_pou_in_standard_types_pous_location():
    """SYNTHETIC: no sample has a POU in types/pous (CODESYS leaves it empty).

    Minimal hand-written PLCopen XML to prove location 1 is read the same way.
    """
    xml = _SYNTHETIC_HEAD + "<types><pous>" + _pou("P1", address="%QX0.0") + "</pous></types>" + _SYNTHETIC_TAIL
    project = parse_string(xml)
    assert project.name == "synthetic.project"
    assert [p.name for p in project.pous] == ["P1"]
    v = project.pous[0].variables[0]
    assert (v.name, v.type, v.scope, v.section, v.address) == ("x", "BOOL", "P1", "local", "%QX0.0")
    assert project.pous[0].body_text == "x := TRUE;"
    assert project.warnings == []


def test_synthetic_project_pou_and_resource_pou_have_separate_ownership():
    """A resource-local POU must not be deduplicated against a project POU."""
    xml = (
        _SYNTHETIC_HEAD
        + "<types><pous>" + _pou("P1", var="fromStandard") + "</pous></types>"
        + "<instances><configurations><configuration name=\"Device\"><resource name=\"Application\">"
        + '<addData><data name="http://www.3s-software.com/plcopenxml/pou" handleUnknown="implementation">'
        + _pou("P1", var="fromCodesys")
        + "</data></addData></resource></configuration></configurations></instances>"
        + _SYNTHETIC_TAIL
    )
    project = parse_string(xml)
    assert [p.name for p in project.pous] == ["P1", "P1"]
    assert project.pous[0].variables[0].name == "fromStandard"
    assert project.pous[1].variables[0].name == "fromCodesys"
    assert [(p.configuration, p.application) for p in project.pous] == [
        (None, None), ("Device", "Application"),
    ]
    assert project.warnings == []


def test_synthetic_generic_section_mapping_warns_only_for_unknown():
    """SYNTHETIC: any *Vars element maps to a section; only unknown ones warn."""
    xml = (
        _SYNTHETIC_HEAD + "<types><pous>"
        + _pou("P1", section="inOutVars")
        + _pou("P2", section="tempVars")
        + _pou("P3", section="weirdVars")
        + "</pous></types>" + _SYNTHETIC_TAIL
    )
    project = parse_string(xml)
    sections = {p.name: p.variables[0].section for p in project.pous}
    assert sections == {"P1": "inout", "P2": "temp", "P3": "weird"}
    assert "inout" in KNOWN_SECTIONS and "temp" in KNOWN_SECTIONS
    assert project.warnings == ["P3: unrecognised variable section <weirdVars>"]


# --------------------------------------------------------------------------- #
# Error handling and XML safety
# --------------------------------------------------------------------------- #


def test_not_a_plcopen_project_raises():
    with pytest.raises(ParseError, match="not a PLCopen XML project"):
        parse_string("<html><body/></html>")


def test_malformed_xml_raises():
    with pytest.raises(ParseError, match="malformed XML"):
        parse_bytes(b"<project xmlns='http://www.plcopen.org/xml/tc6_0200'>")


def test_missing_file_raises():
    with pytest.raises(ParseError, match="cannot read"):
        parse_file("does/not/exist.xml")


def test_entity_expansion_is_refused():
    """defusedxml must reject a billion-laughs style document instead of expanding it."""
    bomb = (
        '<?xml version="1.0"?>'
        "<!DOCTYPE lolz ["
        '<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        "]>"
        '<project xmlns="http://www.plcopen.org/xml/tc6_0200"><contentHeader name="&lol2;"/></project>'
    )
    with pytest.raises(ParseError, match="refused unsafe XML"):
        parse_string(bomb)


def test_external_entity_is_refused(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("hidden")
    xxe = (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE p [<!ENTITY ext SYSTEM "{secret.as_uri()}">]>'
        '<project xmlns="http://www.plcopen.org/xml/tc6_0200"><contentHeader name="&ext;"/></project>'
    )
    with pytest.raises(ParseError, match="refused unsafe XML"):
        parse_string(xxe)


def test_parse_file_accepts_pathlike_and_bom():
    project = parse_file(SMALL_V1)  # file starts with a UTF-8 BOM
    assert project.name == "conveyor_v1.project"
