"""Regressions grounded in sample 06, without pinning the pending Execute feature."""

from plcdoc import Location, Target, by_target, cross_reference, parse_file

from conftest import SAMPLES


LD_POOL = SAMPLES / "06_ld_pool.xml"


def test_sample06_project_gvl_declarations():
    project = parse_file(LD_POOL)
    assert [(g.name, g.configuration, g.application) for g in project.gvls] == [
        ("GVL_Pool", None, None),
    ]
    assert [(v.identity, v.type, v.section) for v in project.gvls[0].variables] == [
        ((None, None, "GVL_Pool", "gPoolCount"), "INT", "global"),
        ((None, None, "GVL_Pool", "gPoolFlag"), "BOOL", "global"),
    ]
    assert project.warnings == []


def test_sample06_project_pou_external_and_body():
    project = parse_file(LD_POOL)
    assert [(p.name, p.configuration, p.application) for p in project.pous] == [
        ("FB_PoolUser", None, None),
        ("PLC_PRG", "Device", "Application"),
        ("PRG_Ladder", "Device", "Application"),
    ]
    pou = project.pous[0]  # Standard types/pous is visited before resource extensions.
    assert pou.pou_type == "functionBlock"
    assert [(v.identity, v.type, v.section) for v in pou.variables] == [
        ((None, None, "FB_PoolUser", "gPoolCount"), "INT", "external"),
        ((None, None, "FB_PoolUser", "xFlagSeen"), "BOOL", "output"),
    ]
    assert pou.body_language == "ST"
    assert pou.body_text == "gPoolCount := gPoolCount + 1;\nxFlagSeen := GVL_Pool.gPoolFlag;"


def test_sample06_project_external_resolves_with_via():
    xref = cross_reference(parse_file(LD_POOL))
    rows = [r for r in xref.references
            if r.location.unit == "FB_PoolUser" and r.text == "gPoolCount"]
    global_target = Target("variable", None, None, "GVL_Pool", "gPoolCount")
    alias = Target("variable", None, None, "FB_PoolUser", "gPoolCount")
    assert [(r.target, r.access, r.via, r.member, r.member_target, r.location) for r in rows] == [
        (global_target, "write", alias, "", None,
         Location(None, None, "FB_PoolUser", line=1, column=1)),
        (global_target, "read", alias, "", None,
         Location(None, None, "FB_PoolUser", line=1, column=len("gPoolCount := ") + 1)),
    ]
    assert by_target(xref)[global_target] == rows
    assert alias not in by_target(xref)
    assert not [u for u in xref.unresolved if u.location.unit == "FB_PoolUser"]
    assert xref.warnings == []


def test_sample06_qualified_project_global_resolves():
    xref = cross_reference(parse_file(LD_POOL))
    rows = [r for r in xref.references
            if r.location.unit == "FB_PoolUser" and r.text == "GVL_Pool.gPoolFlag"]
    assert [(r.target, r.access, r.via, r.member, r.member_target, r.location) for r in rows] == [
        (Target("variable", None, None, "GVL_Pool", "gPoolFlag"), "read", None, "", None,
         Location(None, None, "FB_PoolUser", line=2, column=len("xFlagSeen := ") + 1)),
    ]


def test_sample06_parenthesized_set_assignment_keeps_depth_guard():
    """Khang compiled this real SP22 line with 0 errors; N5 keeps the depth-0 policy."""
    project = parse_file(LD_POOL)
    pou = next(p for p in project.pous if p.name == "PLC_PRG")
    assert pou.body_text.splitlines()[2] == (
        "IF (bHorn S= bDoorClosed) THEN bLampRun := TRUE; END_IF;"
    )
    rows = [r for r in cross_reference(project).references
            if r.location.unit == "PLC_PRG" and r.location.line == 3]
    assert [(r.text, r.access, r.target, r.location) for r in rows] == [
        (name, access, Target("variable", "Device", "Application", "PLC_PRG", name),
         Location("Device", "Application", "PLC_PRG", line=3, column=len(prefix) + 1))
        for name, access, prefix in [
            ("bHorn", "read", "IF ("),
            ("bDoorClosed", "read", "IF (bHorn S= "),
            ("bLampRun", "write", "IF (bHorn S= bDoorClosed) THEN "),
        ]
    ]
