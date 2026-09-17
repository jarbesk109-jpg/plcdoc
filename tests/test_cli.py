"""Command line: plcdoc parse FILE [--json]."""

import json
import subprocess
import sys

import pytest

from plcdoc.cli import main
from plcdoc.render import markdown_table

from conftest import LARGE, SMALL_V1, TYPES_QUALIFIERS


def test_parse_prints_io_table_and_variables(capsys):
    assert main(["parse", str(SMALL_V1)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# conveyor_v1.project")
    assert "Product: CODESYS V3.5 SP22 Patch 3" in out
    assert "## I/O table (7)" in out
    assert "## Variables (10)" in out
    lines = out.splitlines()
    io_lines = [ln for ln in lines if ln.startswith("| %")]
    assert [ln.split("|")[1].strip() for ln in io_lines] == [
        "%IX0.0", "%IX0.1", "%IX0.2", "%IX0.3", "%QX0.0", "%QX0.1", "%QX0.2",
    ]
    assert "| %IX0.0  | input     | bStart    | BOOL | PLC_PRG | Nút Start (NO)" in out
    assert "| PLC_PRG | local   | iPreset   | INT  |         | 10      |" in out


def test_parse_large_lists_gvl_and_all_pous(capsys):
    assert main(["parse", str(LARGE)]) == 0
    out = capsys.readouterr().out
    assert "POUs: PLC_PRG, FB_Motor, FC_Scale, PRG_Alarm" in out
    assert "Global variable lists: GVL_IO" in out
    assert "## I/O table (20)" in out
    assert "## Variables (36)" in out
    assert out.index("| %IX0.7 ") < out.index("| %IX1.0 ") < out.index("| %IW10 ")


def test_json_output_is_deterministic_and_sorted(capsys):
    assert main(["parse", str(SMALL_V1), "--json"]) == 0
    first = capsys.readouterr().out
    assert main(["parse", str(SMALL_V1), "--json"]) == 0
    second = capsys.readouterr().out
    assert first == second

    data = json.loads(first)
    assert list(data) == sorted(data)
    assert data["name"] == "conveyor_v1.project"
    pou = data["pous"][0]
    assert list(pou) == sorted(pou)
    assert [v["name"] for v in pou["variables"]][:3] == ["bStart", "bStop", "bSensor"]
    assert pou["variables"][0]["comment"] == "Nút Start (NO)"  # not \\u-escaped
    assert data["tasks"] == [
        {
            "interval": "PT0.02S", "name": "MainTask", "priority": 1,
            "configuration": "Device", "application": "Application",
            "programs": [{"instance_name": "PLC_PRG", "type_name": "PLC_PRG"}],
        }
    ]
    assert data["warnings"] == []


def test_missing_file_is_an_error(capsys):
    assert main(["parse", "nope.xml"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("plcdoc: cannot read nope.xml")


def test_not_plcopen_file_is_an_error(tmp_path, capsys):
    bad = tmp_path / "bad.xml"
    bad.write_text("<html/>")
    assert main(["parse", str(bad)]) == 1
    assert "not a PLCopen XML project" in capsys.readouterr().err


def test_parse_requires_a_file():
    with pytest.raises(SystemExit):
        main(["parse"])


def test_module_entry_point_runs():
    result = subprocess.run(
        [sys.executable, "-m", "plcdoc", "parse", str(SMALL_V1), "--json"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.decode("utf-8"))["name"] == "conveyor_v1.project"


def test_markdown_table_escapes_pipes_and_none():
    text = markdown_table(("A", "B"), [("x|y", None), ("long value", 1)])
    assert text.splitlines() == [
        "| A          | B |",
        "|------------|---|",
        "| x\\|y       |   |",
        "| long value | 1 |",
    ]


def test_sample04_json_exposes_lossless_model(capsys):
    assert main(["parse", str(TYPES_QUALIFIERS), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert len(data["gvls"]) == 2
    extra = {v["name"]: v for v in data["gvls"][1]["variables"]}
    assert extra["diTotalCount"]["retain"] and extra["MAX_ZONES"]["constant"]
    assert extra["aTemps"]["type"] == "ARRAY[1..4] OF REAL"
    prg = data["pous"][0]
    spare = next(v for v in prg["variables"] if v["name"] == "aSpare")
    assert spare["derived_types"] == ["FB_Motor"]
    assert spare["configuration"] == "Device" and spare["application"] == "Application"
    alarm = next(p for p in data["pous"] if p["name"] == "PRG_Alarm")
    contact = next(n for n in alarm["graphical_body"] if n["kind"] == "contact")
    assert contact["variable"] == "bDoorClosed" and contact["negated"]
    assert contact["incoming_ref_local_ids"] == ["0"]
    assert alarm["body_xml"] and contact["xml"]


def test_markdown_renders_canonical_xml_as_text():
    table = markdown_table(("Initial",), [('<simpleValue value="A&amp;B"/>',)])
    assert '&lt;simpleValue value="A&amp;amp;B"/&gt;' in table
    assert "<simpleValue" not in table
