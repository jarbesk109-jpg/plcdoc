"""I/O table and variable list (plcdoc.tables)."""

from plcdoc.model import Pou, Project, Variable
from plcdoc.tables import io_table, variable_table


def test_small_io_table_rows_and_order(small):
    rows = io_table(small)
    assert [(r.address, r.direction, r.name) for r in rows] == [
        ("%IX0.0", "input", "bStart"),
        ("%IX0.1", "input", "bStop"),
        ("%IX0.2", "input", "bSensor"),
        ("%IX0.3", "input", "bReset"),
        ("%QX0.0", "output", "bMotor"),
        ("%QX0.1", "output", "bLampRun"),
        ("%QX0.2", "output", "bLampDone"),
    ]
    assert rows[0].type == "BOOL"
    assert rows[0].scope == "PLC_PRG"
    assert rows[0].comment == "Nút Start (NO)"


def test_large_io_table_natural_order(large):
    rows = io_table(large)
    assert [r.address for r in rows] == [
        "%IX0.0", "%IX0.1", "%IX0.2", "%IX0.3", "%IX0.4", "%IX0.5", "%IX0.6", "%IX0.7",
        "%IX1.0", "%IX1.1", "%IX1.2",  # byte 1 after bit 0.7, not string-sorted
        "%IW10", "%IW12",  # words after bits within the input area
        "%QX0.0", "%QX0.1", "%QX0.2", "%QX0.3", "%QX0.4",
        "%QW10",
        "%MX0.0",
    ]
    assert [r.direction for r in rows].count("input") == 13
    assert [r.direction for r in rows].count("output") == 6
    assert [r.direction for r in rows].count("memory") == 1
    assert {r.scope for r in rows} == {"GVL_IO"}
    # unaddressed globals are not I/O
    assert "rTankLevel" not in {r.name for r in rows}


def test_io_table_puts_unparseable_addresses_last():
    project = Project(
        name="t",
        product_version="",
        pous=[
            Pou(
                name="P",
                pou_type="program",
                variables=[
                    Variable("weird", "BOOL", "P", "local", address="AT_SOMETHING"),
                    Variable("q", "BOOL", "P", "local", address="%QX0.0"),
                    Variable("i", "BOOL", "P", "local", address="%IX0.0"),
                    Variable("none", "BOOL", "P", "local"),
                ],
            )
        ],
    )
    rows = io_table(project)
    assert [(r.name, r.direction) for r in rows] == [("i", "input"), ("q", "output"), ("weird", "")]


def test_variable_table_is_parse_order_gvl_first(large):
    variables = variable_table(large)
    assert len(variables) == 36
    assert variables[0].scope == "GVL_IO"
    assert variables[-1].scope == "FC_Scale"
