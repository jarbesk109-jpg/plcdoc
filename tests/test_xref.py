"""Cross-reference (Decision 011): sample 05 and 03 oracles, plus SYNTHETIC scope cases.

Rows are ``(unit, line, column, text, access, target, member, member_target)``
with targets written ``kind:scope.name``. Every target in the samples is owned
by ("Device", "Application"); the owner is asserted separately.
"""

from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from plcdoc import Target, by_target, cross_reference, parse_file
from plcdoc.parser import parse_element

from conftest import DRIVE_OOP, LARGE, TYPES_QUALIFIERS

NS = {"p": "http://www.plcopen.org/xml/tc6_0200"}
PREFIX = "{" + NS["p"] + "}"
XHTML = "{http://www.w3.org/1999/xhtml}xhtml"
KIND = {"variable": "v", "field": "f", "method": "m", "property": "p", "action": "a", "result": "r", "pou": "pou"}
P, F, A, M, G, S = (
    "PLC_PRG", "FB_Drive", "FB_Drive.A_Reset", "FB_Drive.M_Start", "FB_Drive.P_Speed.Get", "FB_Drive.P_Speed.Set",
)


def _t(target):
    return None if target is None else f"{KIND[target.kind]}:{target.scope}.{target.name}"


def _row(r):
    return (r.location.unit, r.location.line, r.location.column, r.text, r.access,
            _t(r.target), r.member, _t(r.member_target))


def _short(r):
    return (r.text, r.access, _t(r.target), r.member, _t(r.member_target))


def _unresolved(x):
    return [(u.text, u.access, u.reason) for u in x.unresolved]


def _set_body(root, unit, text):
    """Replace the ST text of a POU ("PLC_PRG"), action ("FB.A") or method ("FB.M") body."""
    pou, _, member = unit.partition(".")
    elem = root.find(f".//p:pou[@name='{pou}']", NS)
    if member:
        action = elem.find(f".//p:action[@name='{member}']", NS)
        elem = action if action is not None else elem.find(f".//p:Method[@name='{member}']", NS)
    elem.find("p:body/p:ST/" + XHTML, NS).text = text


def _with_locals(root, pou, declarations, section="localVars"):
    """SYNTHETIC declarations: {name: '<BOOL/>' | '<derived name="X"/>' | ...} added to *pou*."""
    interface = root.find(f".//p:pou[@name='{pou}']/p:interface", NS)
    holder = interface.find("p:" + section, NS)
    if holder is None:
        holder = ET.SubElement(interface, PREFIX + section)
    for name, type_fragment in declarations.items():
        var = ET.SubElement(holder, PREFIX + "variable", name=name)
        ET.SubElement(var, PREFIX + "type").append(ET.fromstring(f'<type xmlns="{NS["p"]}">{type_fragment}</type>')[0])


# --------------------------------------------------------------------------- #
# Sample oracles
# --------------------------------------------------------------------------- #

SAMPLE05_ROWS = [
    (P, 1, 1, "fbDrive", "call", f"v:{P}.fbDrive", "", None),
    (P, 1, 9, "xEnable", "write", f"v:{P}.fbDrive", "xEnable", f"v:{F}.xEnable"),
    (P, 2, 4, "xStart", "read", f"v:{P}.xStart", "", None),
    (P, 3, 5, "xOk", "write", f"v:{P}.xOk", "", None),
    (P, 3, 12, "fbDrive.M_Start", "call", f"v:{P}.fbDrive", "M_Start", f"m:{F}.M_Start"),
    (P, 3, 28, "rTarget", "write", f"v:{P}.fbDrive", "M_Start.rTarget", f"v:{M}.rTarget"),
    (P, 4, 5, "xStart", "write", f"v:{P}.xStart", "", None),
    (P, 6, 1, "fbDrive.P_Speed", "write", f"v:{P}.fbDrive", "P_Speed", f"p:{F}.P_Speed"),
    (P, 7, 1, "rActual", "write", f"v:{P}.rActual", "", None),
    (P, 7, 12, "fbDrive.P_Speed", "read", f"v:{P}.fbDrive", "P_Speed", f"p:{F}.P_Speed"),
    (P, 8, 8, "fbDrive.xRunning", "read", f"v:{P}.fbDrive", "xRunning", f"v:{F}.xRunning"),
    (P, 9, 5, "fbDrive.A_Reset", "call", f"v:{P}.fbDrive", "A_Reset", f"a:{F}.A_Reset"),
    (F, 1, 1, "xRunning", "write", f"v:{F}.xRunning", "", None),
    (F, 1, 13, "xEnable", "read", f"v:{F}.xEnable", "", None),
    (F, 1, 26, "stData.eState", "read", f"v:{F}.stData", "eState", "f:ST_Drive.eState"),
    (A, 1, 1, "stData.eState", "write", f"v:{F}.stData", "eState", "f:ST_Drive.eState"),
    (A, 2, 1, "stData.rSpeedSet", "write", f"v:{F}.stData", "rSpeedSet", "f:ST_Drive.rSpeedSet"),
    (M, 1, 1, "xOk", "write", f"v:{M}.xOk", "", None),
    (M, 1, 8, "rTarget", "read", f"v:{M}.rTarget", "", None),
    (M, 2, 4, "xOk", "read", f"v:{M}.xOk", "", None),
    (M, 3, 5, "stData.rSpeedSet", "write", f"v:{F}.stData", "rSpeedSet", "f:ST_Drive.rSpeedSet"),
    (M, 3, 25, "rTarget", "read", f"v:{M}.rTarget", "", None),
    (M, 4, 5, "stData.eState", "write", f"v:{F}.stData", "eState", "f:ST_Drive.eState"),
    (M, 6, 1, "M_Start", "write", f"r:{M}.M_Start", "", None),
    (M, 6, 12, "xOk", "read", f"v:{M}.xOk", "", None),
    (G, 1, 2, "P_Speed", "write", f"r:{G}.P_Speed", "", None),
    (G, 1, 13, "rSpeed", "read", f"v:{F}.rSpeed", "", None),
    (S, 1, 1, "rSpeed", "write", f"v:{F}.rSpeed", "", None),
    (S, 1, 11, "P_Speed", "read", f"r:{S}.P_Speed", "", None),
]


def test_sample05_references(drive_oop):
    x = cross_reference(drive_oop)
    assert [_row(r) for r in x.references] == SAMPLE05_ROWS
    assert len(x.references) == 29
    assert x.unresolved == [] and x.warnings == []
    assert not any("E_DriveState" in r.text for r in x.references)
    for r in x.references:
        assert (r.location.configuration, r.location.application) == ("Device", "Application")
        assert (r.target.configuration, r.target.application) == ("Device", "Application")
        assert r.location.local_id is None and r.via is None
    results = [r.target for r in x.references if r.target.kind == "result"]
    assert results[1:] == [
        Target("result", "Device", "Application", G, "P_Speed"),
        Target("result", "Device", "Application", S, "P_Speed"),
    ]


def test_sample03_references_use_globals_pous_and_library_types(large):
    x = cross_reference(large)
    rows = {(r.location.unit, r.location.line, r.location.column): _short(r) for r in x.references}
    assert rows[("PLC_PRG", 1, 15)] == ("bEStopOK", "read", "v:GVL_IO.bEStopOK", "", None)
    assert rows[("PLC_PRG", 13, 1)] == ("PRG_Alarm", "call", "pou:PRG_Alarm.PRG_Alarm", "", None)
    assert rows[("PLC_PRG", 7, 15)] == ("FC_Scale", "call", "pou:FC_Scale.FC_Scale", "", None)
    assert rows[("PLC_PRG", 7, 24)] == ("iRaw", "write", "pou:FC_Scale.FC_Scale", "iRaw", "v:FC_Scale.iRaw")
    assert rows[("PLC_PRG", 7, 32)] == ("iTankLevelRaw", "read", "v:GVL_IO.iTankLevelRaw", "", None)
    assert rows[("PLC_PRG", 3, 90)] == ("bRun", "read", "v:PLC_PRG.fbConv1", "bRun", "v:FB_Motor.bRun")
    assert rows[("PLC_PRG", 3, 98)] == ("bMotor1", "write", "v:GVL_IO.bMotor1", "", None)
    assert rows[("FB_Motor", 1, 10)] == ("IN", "write", "v:FB_Motor.tonFault", "IN", None)
    assert rows[("FB_Motor", 2, 11)] == ("tonFault.Q", "read", "v:FB_Motor.tonFault", "Q", None)
    assert rows[("FC_Scale", 1, 1)] == ("FC_Scale", "write", "r:FC_Scale.FC_Scale", "", None)
    assert rows[("FC_Scale", 1, 33)] == ("iRaw", "read", "v:FC_Scale.iRaw", "", None)
    assert _unresolved(x) == [("REAL_TO_INT", "call", "undeclared"), ("INT_TO_REAL", "call", "undeclared")]
    assert x.warnings == []
    assert not any("T#" in r.text or "500" in r.text for r in x.references)


def test_by_target_indexes_head_and_member(drive_oop):
    x = cross_reference(drive_oop)
    grouped = by_target(x)
    owner = ("Device", "Application")
    x_running = grouped[Target("variable", *owner, F, "xRunning")]
    assert [_row(r)[:3] for r in x_running] == [(P, 8, 8), (F, 1, 1)]
    fb_drive = grouped[Target("variable", *owner, P, "fbDrive")]
    assert (P, 8, 8) in [_row(r)[:3] for r in fb_drive]
    for references in grouped.values():
        assert len(references) == len(set(map(id, references)))
    with_member = sum(1 for r in x.references if r.member_target is not None)
    assert with_member == 12
    assert sum(len(v) for v in grouped.values()) == 29 + with_member


def test_reference_order_is_deterministic(drive_oop):
    assert cross_reference(drive_oop) == cross_reference(parse_file(DRIVE_OOP))


# --------------------------------------------------------------------------- #
# ST edge cases (SYNTHETIC bodies in a copy of sample 03 or 05)
# --------------------------------------------------------------------------- #

INT, BOOL = "<INT/>", "<BOOL/>"
EDGE_CASES = [
    ("comment-line", LARGE, P, {}, "// bLineReady := FALSE;\nbLineReady := TRUE;",
     [("bLineReady", "write", "v:PLC_PRG.bLineReady", "", None)], []),
    ("comment-block", LARGE, P, {}, "(* bLineReady := FALSE; *) bLineReady := TRUE;",
     [("bLineReady", "write", "v:PLC_PRG.bLineReady", "", None)], []),
    ("comment-c", LARGE, P, {}, "/* bLineReady := FALSE; */ bLineReady := TRUE;",
     [("bLineReady", "write", "v:PLC_PRG.bLineReady", "", None)], []),
    ("string", LARGE, P, {"sMsg": '<string length="20"/>'}, "sMsg := 'a // (* $' b';",
     [("sMsg", "write", "v:PLC_PRG.sMsg", "", None)], []),
    ("pragma", LARGE, P, {}, "{warning 'bLineReady := 1'} bLineReady := TRUE;",
     [("bLineReady", "write", "v:PLC_PRG.bLineReady", "", None)], []),
    ("literals", LARGE, P, {"iVal": INT, "tDelay": "<TIME/>"}, "iVal := 16#FF + INT#5; tDelay := T#5s;",
     [("iVal", "write", "v:PLC_PRG.iVal", "", None), ("tDelay", "write", "v:PLC_PRG.tDelay", "", None)], []),
    ("bit-access", LARGE, P, {"xBit": BOOL, "wStatus": "<WORD/>"}, "xBit := wStatus.3;",
     [("xBit", "write", "v:PLC_PRG.xBit", "", None), ("wStatus", "read", "v:PLC_PRG.wStatus", "", None)], []),
    ("case-insensitive", LARGE, P, {"xStart": BOOL}, "XSTART := TRUE;",
     [("XSTART", "write", "v:PLC_PRG.xStart", "", None)], []),
    ("set-reset", LARGE, P, {"xA": BOOL, "xB": BOOL}, "xA S= xB; xA R= xB;",
     [("xA", "write", "v:PLC_PRG.xA", "", None), ("xB", "read", "v:PLC_PRG.xB", "", None),
      ("xA", "write", "v:PLC_PRG.xA", "", None), ("xB", "read", "v:PLC_PRG.xB", "", None)], []),
    ("ref-assign", LARGE, P, {"refX": "<pointer><baseType><INT/></baseType></pointer>", "iVal": INT},
     "refX REF= iVal;",
     [("refX", "write", "v:PLC_PRG.refX", "", None), ("iVal", "read", "v:PLC_PRG.iVal", "", None)], []),
    ("for-loop", LARGE, P, {"i": INT, "n": INT, "iVal": INT}, "FOR i := 1 TO n DO iVal := i; END_FOR",
     [("i", "write", "v:PLC_PRG.i", "", None), ("n", "read", "v:PLC_PRG.n", "", None),
      ("iVal", "write", "v:PLC_PRG.iVal", "", None), ("i", "read", "v:PLC_PRG.i", "", None)], []),
    ("array-index", LARGE, P, {"a": '<array><dimension lower="1" upper="3"/><baseType><INT/></baseType></array>',
                               "i": INT, "iVal": INT}, "iVal := a[i];",
     [("iVal", "write", "v:PLC_PRG.iVal", "", None), ("a", "read", "v:PLC_PRG.a", "", None),
      ("i", "read", "v:PLC_PRG.i", "", None)], []),
    ("adr", LARGE, P, {"pAddr": "<pointer><baseType><INT/></baseType></pointer>", "iVal": INT},
     "pAddr := ADR(iVal);",
     [("pAddr", "write", "v:PLC_PRG.pAddr", "", None), ("iVal", "read", "v:PLC_PRG.iVal", "", None)],
     [("ADR", "call", "undeclared")]),
    ("this", LARGE, "FB_Motor", {}, "THIS^.bRun := TRUE;",
     [("THIS^.bRun", "write", "v:FB_Motor.bRun", "", None)], []),
    ("super", LARGE, "FB_Motor", {}, "SUPER^.M();", [], [("SUPER^.M", "call", "inheritance")]),
    ("qualified-global", LARGE, P, {}, "GVL_IO.bStart1 := TRUE;",
     [("GVL_IO.bStart1", "write", "v:GVL_IO.bStart1", "", None)], []),
    ("other-program-variable", LARGE, "FB_Motor", {}, "bRun := PLC_PRG.bLineReady;",
     [("bRun", "write", "v:FB_Motor.bRun", "", None), ("PLC_PRG.bLineReady", "read", "v:PLC_PRG.bLineReady", "", None)], []),
    ("unqualified-enum-literal", DRIVE_OOP, A, {}, "stData.eState := IDLE;",
     [("stData.eState", "write", "v:FB_Drive.stData", "eState", "f:ST_Drive.eState")], []),
    ("library-namespace", LARGE, P, {"iVal": INT}, "iVal := Standard.SomeConst;",
     [("iVal", "write", "v:PLC_PRG.iVal", "", None)], [("Standard.SomeConst", "read", "undeclared")]),
    ("pointer-deref", DRIVE_OOP, P, {"pData": '<pointer><baseType><derived name="ST_Drive"/></baseType></pointer>'},
     "rActual := pData^.rSpeedSet;",
     [("rActual", "write", "v:PLC_PRG.rActual", "", None), ("pData^.rSpeedSet", "read", "v:PLC_PRG.pData", "rSpeedSet", None)], []),
]


@pytest.mark.parametrize(
    "sample,unit,declarations,body,expected,unresolved", [case[1:] for case in EDGE_CASES],
    ids=[case[0] for case in EDGE_CASES],
)
def test_st_edge_cases(sample, unit, declarations, body, expected, unresolved):
    root = ET.parse(sample).getroot()
    _with_locals(root, unit.partition(".")[0], declarations)
    _set_body(root, unit, body)
    x = cross_reference(parse_element(root))
    rows = [_short(r) for r in x.references if r.location.unit == unit]
    assert rows == expected
    assert [(u.text, u.access, u.reason) for u in x.unresolved if u.location.unit == unit] == unresolved


@pytest.mark.parametrize("literal", [
    "INT#5", "REAL#1.5e+3", "REAL#-1.5e-3", "WORD#16#FF", "BOOL#TRUE",
    "T#5s", "TIME#1h_2m_3.5s", "LTIME#-5ms", "D#2026-09-20", "DT#2026-09-20-12:34:56",
    "TOD#12:34:56.5",
])
@pytest.mark.parametrize("operator", ["+", "-"])
def test_typed_literals_stop_before_adjacent_operators(literal, operator):
    """SYNTHETIC: literal-internal signs must not consume the following variable occurrence."""
    root = ET.parse(LARGE).getroot()
    _with_locals(root, P, {"iVal": INT})
    prefix = "iVal := "
    _set_body(root, P, f"{prefix}{literal}{operator}iVal;")
    x = cross_reference(parse_element(root))
    rows = [r for r in x.references if r.location.unit == P]
    assert [(r.text, r.access, r.location.line, r.location.column) for r in rows] == [
        ("iVal", "write", 1, 1),
        ("iVal", "read", 1, len(prefix) + len(literal) + 2),
    ]
    assert all(r.target == Target("variable", "Device", "Application", P, "iVal") for r in rows)
    assert [u for u in x.unresolved if u.location.unit == P] == []


@pytest.mark.parametrize("symbol", ["R", "S", "REF", "r", "s", "ref"])
def test_word_assignment_names_are_read_in_equalities(symbol):
    """SYNTHETIC: spaces around equality cannot hide R/S/REF; set/reset still writes its lhs."""
    for gap in ("", " ", "\t"):
        root = ET.parse(LARGE).getroot()
        _with_locals(root, P, {symbol: BOOL})
        body = f"IF {symbol}{gap}=TRUE THEN {symbol} := FALSE; END_IF {symbol} S= TRUE; {symbol} R= FALSE;"
        _set_body(root, P, body)
        x = cross_reference(parse_element(root))
        rows = [r for r in x.references if r.location.unit == P]
        assert [(r.text, r.access) for r in rows] == [
            (symbol, "read"), (symbol, "write"), (symbol, "write"), (symbol, "write"),
        ]
        assert rows[0].location.column == 4
        assert rows[1].location.column == body.index("THEN ") + len("THEN ") + 1
        assert all(r.target == Target("variable", "Device", "Application", P, symbol) for r in rows)
        assert [u for u in x.unresolved if u.location.unit == P] == []


ONE_LINE = (
    "IF a THEN b := 1; ELSIF c THEN d := 2; ELSE e := 3; END_IF "
    "WHILE f DO g := 4; END_WHILE REPEAT h := 5; UNTIL k END_REPEAT "
    "CASE m OF 1: n := 6; 2, 3: o := 7; ELSE p := 8; END_CASE q := 9;"
)
MULTI_LINE = (
    "IF a THEN\n    b := 1;\nELSIF c THEN\n    d := 2;\nELSE\n    e := 3;\nEND_IF\n"
    "WHILE f DO\n    g := 4;\nEND_WHILE\nREPEAT\n    h := 5;\nUNTIL k\nEND_REPEAT\n"
    "CASE m OF\n    1:\n        n := 6;\n    2, 3:\n        o := 7;\nELSE\n    p := 8;\nEND_CASE\nq := 9;"
)


@pytest.mark.parametrize("body", [ONE_LINE, MULTI_LINE], ids=["one-line", "multi-line"])
def test_statement_boundaries(body):
    root = ET.parse(LARGE).getroot()
    _with_locals(root, P, {name: INT for name in "abcdefghkmnopq"})
    _set_body(root, P, body)
    x = cross_reference(parse_element(root))
    rows = [(r.text, r.access) for r in x.references if r.location.unit == P]
    assert sorted(t for t, a in rows if a == "write") == sorted("bdeghnopq")
    assert sorted(t for t, a in rows if a == "read") == sorted("acfkm")
    assert len(rows) == 14
    assert [u for u in x.unresolved if u.location.unit == P] == []


def test_nested_call_and_index_state():
    root = ET.parse(DRIVE_OOP).getroot()
    array = '<array><dimension lower="1" upper="3"/><baseType><REAL/></baseType></array>'
    _with_locals(root, P, {"a": array, "b": array, "i": INT, "c": "<REAL/>"})
    _set_body(root, P, "a[fbDrive.M_Start(rTarget := b[i])] := c;")
    x = cross_reference(parse_element(root))
    assert [_short(r) for r in x.references if r.location.unit == P] == [
        ("a", "write", "v:PLC_PRG.a", "", None),
        ("fbDrive.M_Start", "call", "v:PLC_PRG.fbDrive", "M_Start", "m:FB_Drive.M_Start"),
        ("rTarget", "write", "v:PLC_PRG.fbDrive", "M_Start.rTarget", "v:FB_Drive.M_Start.rTarget"),
        ("b", "read", "v:PLC_PRG.b", "", None),
        ("i", "read", "v:PLC_PRG.i", "", None),
        ("c", "read", "v:PLC_PRG.c", "", None),
    ]
    assert x.unresolved == []


# --------------------------------------------------------------------------- #
# VAR_EXTERNAL, VAR_IN_OUT, owner chain, shadowing, member walk (SYNTHETIC)
# --------------------------------------------------------------------------- #


def test_var_external_is_an_alias():
    root = ET.parse(LARGE).getroot()
    _with_locals(root, P, {"bHorn": BOOL, "bMissing": BOOL}, section="externalVars")
    _set_body(root, P, "bHorn := TRUE;\nGVL_IO.bHorn := FALSE;\nbMissing := TRUE;")
    _set_body(root, "FB_Motor", "PLC_PRG.bHorn := TRUE;")
    project = parse_element(root)
    x = cross_reference(project)
    owner = ("Device", "Application")
    global_horn = Target("variable", *owner, "GVL_IO", "bHorn")
    external_horn = Target("variable", *owner, P, "bHorn")
    rows = [(r.location.unit, r.text, r.access, r.target, r.via) for r in x.references
            if r.target.name == "bHorn"]
    assert rows == [
        (P, "bHorn", "write", global_horn, external_horn),
        (P, "GVL_IO.bHorn", "write", global_horn, None),
        ("FB_Motor", "PLC_PRG.bHorn", "write", global_horn, external_horn),
        ("PRG_Alarm", "bHorn", "write", global_horn, None),  # the ladder coil of sample 03
    ]
    declared = {(v.name, v.section) for v in project.pous[0].variables}
    assert ("bHorn", "external") in declared
    assert external_horn not in by_target(x)
    assert _unresolved(x)[:1] == [("bMissing", "write", "external without global")]
    assert x.warnings == []


@pytest.mark.parametrize("unit,element_path", [
    (M, ".//p:Method[@name='M_Start']"),
    (G, ".//p:GetAccessor"),
    (S, ".//p:SetAccessor"),
])
def test_unit_externals_normalise_or_report_missing_global(unit, element_path):
    """SYNTHETIC: a method/accessor external is an alias, including its read occurrences."""
    root = ET.parse(DRIVE_OOP).getroot()
    element = root.find(element_path, NS)
    section = ET.SubElement(element.find("p:interface", NS), PREFIX + "externalVars")
    _declare_global(section, "xShared")
    _declare_global(section, "xMissing")
    gvl = ET.SubElement(root.find(".//p:resource", NS), PREFIX + "globalVars", name="Shared")
    _declare_global(gvl, "xShared")
    element.find("p:body/p:ST/" + XHTML, NS).text = "xShared := xShared; xMissing := xMissing;"
    x = cross_reference(parse_element(root))
    global_target = Target("variable", "Device", "Application", "Shared", "xShared")
    alias = Target("variable", "Device", "Application", unit, "xShared")
    rows = [r for r in x.references if r.location.unit == unit]
    assert [(r.text, r.access, r.target, r.member, r.member_target, r.via) for r in rows] == [
        ("xShared", "write", global_target, "", None, alias),
        ("xShared", "read", global_target, "", None, alias),
    ]
    assert [(u.text, u.access, u.reason) for u in x.unresolved if u.location.unit == unit] == [
        ("xMissing", "write", "external without global"),
        ("xMissing", "read", "external without global"),
    ]
    assert by_target(x)[global_target] == rows
    assert alias not in by_target(x)
    assert x.warnings == []


@pytest.mark.parametrize("prefix", ["fbConv1", "FB_Motor"])
def test_qualified_externals_normalise_or_report_missing_global(prefix):
    root = ET.parse(LARGE).getroot()
    _with_locals(root, "FB_Motor", {"bHorn": BOOL, "bMissing": BOOL}, section="externalVars")
    _set_body(root, P, f"{prefix}.bHorn := TRUE; {prefix}.bMissing := FALSE;")
    x = cross_reference(parse_element(root))
    owner = ("Device", "Application")
    global_target = Target("variable", *owner, "GVL_IO", "bHorn")
    instance = Target("variable", *owner, P, "fbConv1")
    alias = Target("variable", *owner, "FB_Motor", "bHorn")
    rows = [r for r in x.references if r.location.unit == P]
    assert [(r.text, r.access, r.target, r.member, r.member_target, r.via) for r in rows] == [
        (f"{prefix}.bHorn", "write", instance, "bHorn", global_target, None)
        if prefix == "fbConv1" else
        (f"{prefix}.bHorn", "write", global_target, "", None, alias),
    ]
    assert rows[0] in by_target(x)[global_target]
    assert alias not in by_target(x)
    assert [(u.text, u.access, u.reason) for u in x.unresolved if u.location.unit == P] == [
        (f"{prefix}.bMissing", "write", "external without global"),
    ]
    assert x.warnings == []


def test_var_external_ambiguity_warns():
    root = ET.parse(TYPES_QUALIFIERS).getroot()
    for gvl in root.findall(".//p:resource/p:globalVars", NS):
        _declare_global(gvl, "bDup")
    _with_locals(root, P, {"bDup": BOOL}, section="externalVars")
    _set_body(root, P, "bDup := TRUE;")
    x = cross_reference(parse_element(root))
    assert [_short(r) for r in x.references if r.location.unit == P] == [
        ("bDup", "write", "v:GVL_IO.bDup", "", None),
    ]
    assert x.warnings == ["ambiguous global 'bDup': GVL_IO, GVL_Extra (using GVL_IO)"]


def _declare_global(gvl, name, type_fragment=BOOL):
    var = ET.Element(PREFIX + "variable", name=name)
    ET.SubElement(var, PREFIX + "type").append(ET.fromstring(f'<type xmlns="{NS["p"]}">{type_fragment}</type>')[0])
    gvl.insert(len(gvl.findall("p:variable", NS)), var)


def _in_out_project():
    """FB_Motor gains io (VAR_IN_OUT) right after the inputs and ioc (VAR_IN_OUT CONSTANT) after that."""
    root = ET.parse(LARGE).getroot()
    interface = root.find(".//p:pou[@name='FB_Motor']/p:interface", NS)
    inputs = interface.find("p:inputVars", NS)
    position = list(interface).index(inputs) + 1
    for offset, (name, constant) in enumerate([("io", None), ("ioc", "true")]):
        section = ET.Element(PREFIX + "inOutVars", **({"constant": constant} if constant else {}))
        var = ET.SubElement(section, PREFIX + "variable", name=name)
        ET.SubElement(ET.SubElement(var, PREFIX + "type"), PREFIX + "INT")
        interface.insert(position + offset, section)
    _with_locals(root, P, {"v1": INT, "v2": INT})
    return root


@pytest.mark.parametrize("body,expected,unresolved", [
    ("fbConv1(io := v1, ioc := v2);", [
        ("fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
        ("io", "readwrite", "v:PLC_PRG.fbConv1", "io", "v:FB_Motor.io"),
        ("v1", "readwrite", "v:PLC_PRG.v1", "", None),
        ("ioc", "read", "v:PLC_PRG.fbConv1", "ioc", "v:FB_Motor.ioc"),
        ("v2", "read", "v:PLC_PRG.v2", "", None),
    ], []),
    ("fbConv1(bStart1, bStop1, bFault1, bLineReady, v1, v2);", [
        ("fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
        ("bStart1", "read", "v:GVL_IO.bStart1", "", None),
        ("bStop1", "read", "v:GVL_IO.bStop1", "", None),
        ("bFault1", "read", "v:GVL_IO.bFault1", "", None),
        ("bLineReady", "read", "v:PLC_PRG.bLineReady", "", None),
        ("v1", "readwrite", "v:PLC_PRG.v1", "", None),
        ("v2", "read", "v:PLC_PRG.v2", "", None),
    ], []),
    ("INT_TO_REAL(v1);", [("v1", "read", "v:PLC_PRG.v1", "", None)], [("INT_TO_REAL", "call", "undeclared")]),
], ids=["named", "positional", "unknown-callee"])
def test_var_in_out_actuals(body, expected, unresolved):
    root = _in_out_project()
    _set_body(root, P, body)
    project = parse_element(root)
    formals = [(v.name, v.section, v.constant) for v in project.pous[1].variables if v.section != "local"]
    assert formals == [
        ("bStart", "input", False), ("bStop", "input", False), ("bFault", "input", False),
        ("bInterlock", "input", False), ("io", "inout", False), ("ioc", "inout", True),
        ("bRun", "output", False), ("bAlarm", "output", False),
    ]
    x = cross_reference(project)
    assert [_short(r) for r in x.references if r.location.unit == P] == expected
    assert [(u.text, u.access, u.reason) for u in x.unresolved if u.location.unit == P] == unresolved


@pytest.mark.parametrize("named", [True, False], ids=["named", "positional"])
def test_inout_expression_actual_is_read_but_bare_actual_is_readwrite(named):
    """SYNTHETIC unclassifiable actual: use the expression fallback, not in-out direction."""
    root = _in_out_project()
    prefix = "io := " if named else "TRUE, FALSE, FALSE, TRUE, "
    lines = [f"fbConv1({prefix}v1 + 1);", f"fbConv1({prefix}v1);"]
    _set_body(root, P, "\n".join(lines))
    x = cross_reference(parse_element(root))
    rows = [r for r in x.references if r.location.unit == P]
    expected = []
    for actual_access in ("read", "readwrite"):
        expected.append(("fbConv1", "call", "v:PLC_PRG.fbConv1", "", None))
        if named:
            expected.append(("io", "readwrite", "v:PLC_PRG.fbConv1", "io", "v:FB_Motor.io"))
        expected.append(("v1", actual_access, "v:PLC_PRG.v1", "", None))
    assert [_short(r) for r in rows] == expected
    assert [(r.location.line, r.location.column) for r in rows if r.text == "v1"] == [
        (line_number, len("fbConv1(" + prefix) + 1) for line_number in range(1, 3)
    ]
    assert [u for u in x.unresolved if u.location.unit == P] == []


def _synthetic_pou(name, interface):
    return ET.fromstring(f'<pou xmlns="{NS["p"]}" name="{name}" pouType="functionBlock">'
                         f'<interface>{interface}</interface></pou>')


@pytest.mark.parametrize("shape", ["variable", "inline-field", "inline-array-field"])
@pytest.mark.parametrize("section,formal_access,actual_access", [
    ("inOutVars", "readwrite", "readwrite"), ("outputVars", "read", "write"),
])
def test_nested_callable_uses_final_declaration_owner(shape, section, formal_access, actual_access):
    """SYNTHETIC: the project-level member's type must not bind an application-local namesake."""
    root = ET.parse(DRIVE_OOP).getroot()
    project_pous = root.find("./p:types/p:pous", NS)
    arg = '<variable name="arg"><type><INT/></type></variable>'
    project_pous.append(_synthetic_pou("FB_Child", f'<{section}>{arg}</{section}>'))
    wrapper = ET.SubElement(root.find(".//p:resource/p:addData", NS), PREFIX + "data",
                            name="http://www.3s-software.com/plcopenxml/pou")
    wrapper.append(_synthetic_pou("FB_Child", f'<inputVars>{arg}</inputVars>'))
    child_type = '<derived name="FB_Child"/>'
    if shape == "inline-array-field":
        child_type = f'<array><dimension lower="1" upper="2"/><baseType>{child_type}</baseType></array>'
    if shape == "variable":
        declaration = f'<variable name="inner"><type>{child_type}</type></variable>'
        member, called_path, leaf = "inner", "outer.inner", "v:FB_Outer.inner"
    else:
        declaration = ('<variable name="s"><type><struct><variable name="d"><type>' + child_type
                       + '</type></variable></struct></type></variable>')
        member, called_path, leaf = "s.d", "outer.s.d", None
        if shape == "inline-array-field":
            called_path += "[1]"
    project_pous.append(_synthetic_pou("FB_Outer", f'<localVars>{declaration}</localVars>'))
    _with_locals(root, P, {"outer": '<derived name="FB_Outer"/>', "v": INT})
    _set_body(root, P, f"{called_path}(arg := v);")
    x = cross_reference(parse_element(root))
    rows = [r for r in x.references if r.location.unit == P]
    assert [_short(r) for r in rows] == [
        (f"outer.{member}", "call", "v:PLC_PRG.outer", member, leaf),
        ("arg", formal_access, "v:PLC_PRG.outer", f"{member}.arg", "v:FB_Child.arg"),
        ("v", actual_access, "v:PLC_PRG.v", "", None),
    ]
    assert rows[1].member_target == Target("variable", None, None, "FB_Child", "arg")
    assert (rows[0].target.configuration, rows[0].target.application) == ("Device", "Application")
    assert x.unresolved == [] and x.warnings == []


@pytest.mark.parametrize("positional", [False, True], ids=["named", "positional"])
@pytest.mark.parametrize("array_field", [False, True], ids=["field", "array-field"])
def test_inline_field_call_keeps_formal_signature(positional, array_field):
    root = _in_out_project()
    child_type = '<derived name="FB_Motor"/>'
    if array_field:
        child_type = f'<array><dimension lower="1" upper="2"/><baseType>{child_type}</baseType></array>'
    _with_locals(root, P, {"s": f'<struct><variable name="d"><type>{child_type}</type></variable></struct>'})
    actuals = "TRUE, FALSE, FALSE, TRUE, v1, v2" if positional else "io := v1, ioc := v2"
    _set_body(root, P, f"s.d{'[1]' if array_field else ''}({actuals});")
    x = cross_reference(parse_element(root))
    expected = [("s.d", "call", "v:PLC_PRG.s", "d", None)]
    if not positional:
        expected.append(("io", "readwrite", "v:PLC_PRG.s", "d.io", "v:FB_Motor.io"))
    expected.append(("v1", "readwrite", "v:PLC_PRG.v1", "", None))
    if not positional:
        expected.append(("ioc", "read", "v:PLC_PRG.s", "d.ioc", "v:FB_Motor.ioc"))
    expected.append(("v2", "read", "v:PLC_PRG.v2", "", None))
    assert [_short(r) for r in x.references if r.location.unit == P] == expected
    assert [u for u in x.unresolved if u.location.unit == P] == []


def _owner_chain_case(case):
    root = ET.parse(TYPES_QUALIFIERS if case == "two-gvls" else LARGE).getroot()
    if case == "second-application":
        configuration = root.find(".//p:configuration", NS)
        second = deepcopy(configuration.find("p:resource", NS))
        second.set("name", "Application2")
        configuration.append(second)
    elif case == "project-pou":
        data = root.find(".//p:resource/p:addData", NS)
        wrapper = next(d for d in data if d.find("p:pou[@name='FC_Scale']", NS) is not None)
        data.remove(wrapper)
        root.find("./p:types/p:pous", NS).append(wrapper.find("p:pou", NS))
    elif case == "configuration-gvl":
        configuration = root.find(".//p:configuration", NS)
        resource = configuration.find("p:resource", NS)
        gvl = resource.find("p:globalVars", NS)
        resource.remove(gvl)
        configuration.insert(1, gvl)
    elif case == "conflicting-pou":
        data = root.find(".//p:resource/p:addData", NS)
        wrapper = next(d for d in data if d.find("p:pou[@name='FC_Scale']", NS) is not None)
        duplicate = deepcopy(wrapper)
        duplicate.find(".//p:ST/" + XHTML, NS).text = "FC_Scale := 0.0;"
        data.append(duplicate)
    elif case == "two-gvls":
        for gvl in root.findall(".//p:resource/p:globalVars", NS):
            _declare_global(gvl, "bDup")
        _set_body(root, P, "bDup := TRUE;")
    return root


@pytest.mark.parametrize("case", [
    "second-application", "project-pou", "configuration-gvl", "conflicting-pou", "two-gvls",
])
def test_owner_chain_resolution(case):
    x = cross_reference(parse_element(_owner_chain_case(case)))
    calls = [r for r in x.references if r.text == "FC_Scale" and r.access == "call"]
    if case == "second-application":
        by_app = {r.location.application: r.target for r in calls}
        assert by_app["Application"] == Target("pou", "Device", "Application", "FC_Scale", "FC_Scale")
        assert by_app["Application2"] == Target("pou", "Device", "Application2", "FC_Scale", "FC_Scale")
        assert x.warnings == []
    elif case == "project-pou":
        assert {r.target for r in calls} == {Target("pou", None, None, "FC_Scale", "FC_Scale")}
        assert x.warnings == []
    elif case == "configuration-gvl":
        estop = next(r for r in x.references if r.text == "bEStopOK")
        assert estop.target == Target("variable", "Device", None, "GVL_IO", "bEStopOK")
        assert x.warnings == []
    elif case == "conflicting-pou":
        assert {r.target for r in calls} == {Target("pou", "Device", "Application", "FC_Scale", "FC_Scale")}
        assert x.warnings == ["ambiguous POU 'FC_Scale' in Device/Application: using the first definition"]
    else:
        dup = next(r for r in x.references if r.text == "bDup")
        assert dup.target == Target("variable", "Device", "Application", "GVL_IO", "bDup")
        assert x.warnings == ["ambiguous global 'bDup': GVL_IO, GVL_Extra (using GVL_IO)"]


def test_method_local_shadows_fb_variable():
    root = ET.parse(DRIVE_OOP).getroot()
    method = root.find(".//p:Method[@name='M_Start']", NS)
    var = ET.SubElement(method.find("p:interface/p:localVars", NS), PREFIX + "variable", name="rSpeed")
    ET.SubElement(ET.SubElement(var, PREFIX + "type"), PREFIX + "REAL")
    _set_body(root, "FB_Drive.M_Start", "rSpeed := 1.0;")
    x = cross_reference(parse_element(root))
    assert [_short(r) for r in x.references if r.location.unit == M] == [
        ("rSpeed", "write", f"v:{M}.rSpeed", "", None),
    ]
    assert x.warnings == []


@pytest.mark.parametrize("declarations,body,expected", [
    ({"p": '<pointer><baseType><derived name="ST_Drive"/></baseType></pointer>'},
     "rActual := p^.eState;",
     [("rActual", "write", "v:PLC_PRG.rActual", "", None), ("p^.eState", "read", "v:PLC_PRG.p", "eState", None)]),
    ({"s": '<struct><variable name="d"><type><derived name="FB_Drive"/></type></variable></struct>'},
     "xOk := s.d.xRunning; xOk := s.d;",
     [("xOk", "write", "v:PLC_PRG.xOk", "", None),
      ("s.d.xRunning", "read", "v:PLC_PRG.s", "d.xRunning", "v:FB_Drive.xRunning"),
      ("xOk", "write", "v:PLC_PRG.xOk", "", None),
      ("s.d", "read", "v:PLC_PRG.s", "d", None)]),
    ({"arr": '<array><dimension lower="1" upper="2"/><baseType><derived name="FB_Drive"/></baseType></array>'},
     "xOk := arr[1].xRunning;",
     [("xOk", "write", "v:PLC_PRG.xOk", "", None),
      ("arr.xRunning", "read", "v:PLC_PRG.arr", "xRunning", "v:FB_Drive.xRunning")]),  # text drops [1]
], ids=["pointer-to-dut", "inline-struct", "array-of-fb"])
def test_member_walk_uses_type_structure(declarations, body, expected):
    root = ET.parse(DRIVE_OOP).getroot()
    _with_locals(root, P, declarations)
    _set_body(root, P, body)
    project = parse_element(root)
    declared = {v.name: v for v in project.pous[0].variables}
    for name in declarations:
        assert len(declared[name].derived_types) == 1  # derived_types alone cannot tell these apart
    x = cross_reference(project)
    assert [_short(r) for r in x.references if r.location.unit == P] == expected
    assert x.unresolved == []


# --------------------------------------------------------------------------- #
# LD bodies
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("namespace", ["urn:vendor", ""])
@pytest.mark.parametrize("depth", range(1, 7))
def test_member_walk_stops_at_foreign_structural_elements(namespace, depth):
    """SYNTHETIC: every type step, including containers and inline fields, is namespace-sensitive."""
    root = _in_out_project()
    _with_locals(root, P, {"s": '<array><dimension lower="1" upper="2"/><baseType><struct>'
                  '<variable name="d"><type><derived name="FB_Motor"/></type></variable>'
                  '</struct></baseType></array>'})
    path = "/".join(["p:array", "p:baseType", "p:struct", "p:variable", "p:type", "p:derived"][:depth])
    var_type = root.find(".//p:pou[@name='PLC_PRG']/p:interface/p:localVars/p:variable[@name='s']/p:type", NS)
    foreign = var_type.find(path, NS)
    local = foreign.tag.rpartition("}")[2]
    foreign.tag = f"{{{namespace}}}{local}" if namespace else local
    _set_body(root, P, "s[1].d.bRun;")
    x = cross_reference(parse_element(root))
    assert [_short(r) for r in x.references if r.location.unit == P] == [
        ("s.d.bRun", "read", "v:PLC_PRG.s", "d.bRun", None),
    ]
    assert [u for u in x.unresolved if u.location.unit == P] == []


@pytest.mark.parametrize("namespace", ["urn:vendor", ""])
@pytest.mark.parametrize("path", ["p:derived", "p:array", "p:array/p:baseType", "p:array/p:baseType/p:derived"])
def test_callable_type_stops_at_foreign_structural_elements(namespace, path):
    """SYNTHETIC: foreign shapes cannot lend a known FB signature to a call."""
    root = _in_out_project()
    is_array = path.startswith("p:array")
    shape = '<derived name="FB_Motor"/>'
    if is_array:
        shape = f'<array><dimension lower="1" upper="2"/><baseType>{shape}</baseType></array>'
    _with_locals(root, P, {"s": shape})
    var_type = root.find(".//p:pou[@name='PLC_PRG']/p:interface/p:localVars/p:variable[@name='s']/p:type", NS)
    foreign = var_type.find(path, NS)
    local = foreign.tag.rpartition("}")[2]
    foreign.tag = f"{{{namespace}}}{local}" if namespace else local
    _set_body(root, P, f"{'s[1]' if is_array else 's'}(io := v1);")
    x = cross_reference(parse_element(root))
    assert [_short(r) for r in x.references if r.location.unit == P] == [
        ("s", "call", "v:PLC_PRG.s", "", None),
        ("io", "write", "v:PLC_PRG.s", "io", None),
        ("v1", "read", "v:PLC_PRG.v1", "", None),
    ]
    assert [u for u in x.unresolved if u.location.unit == P] == []


def _ld_row(r):
    return (r.location.unit, r.location.local_id, r.text, r.access, _t(r.target), r.member, _t(r.member_target))


def test_sample03_ladder_references(large):
    x = cross_reference(large)
    ladder = [r for r in x.references if r.location.unit == "PRG_Alarm"]
    assert [_ld_row(r) for r in ladder] == [
        ("PRG_Alarm", "3", "bDoorClosed", "read", "v:GVL_IO.bDoorClosed", "", None),
        ("PRG_Alarm", "4", "bHorn", "write", "v:GVL_IO.bHorn", "", None),
    ]
    assert all(r.location.line is None and r.location.column is None for r in ladder)


def _pin(group, name, ref=None):
    connection = (
        f'<connectionPointIn><connection refLocalId="{ref[0]}" formalParameter="{ref[1]}"/></connectionPointIn>'
        if ref else "<connectionPointOut/>"
    )
    return f'<{group}><variable formalParameter="{name}">{connection}</variable></{group}>'


def _block_xml(local_id, instance, *pins):
    return f'<block localId="{local_id}" typeName="FB_Motor" instanceName="{instance}">{"".join(pins)}</block>'


def _ld_project(root, *elements):
    """SYNTHETIC: replace PLC_PRG's body in *root* with an LD network made of *elements*."""
    body = root.find(f".//p:pou[@name='{P}']/p:body", NS)
    body.clear()
    body.append(ET.fromstring(f'<LD xmlns="{NS["p"]}">{"".join(elements)}</LD>'))
    return parse_element(root)


def test_ld_block_and_pins():
    project = _ld_project(
        ET.parse(LARGE).getroot(),
        '<inVariable localId="1"><expression>bStart1 AND NOT bStop1</expression><connectionPointOut/></inVariable>',
        _block_xml(2, "fbConv1", _pin("inputVariables", "bStart", ("1", "")), _pin("outputVariables", "bRun")),
        '<outVariable localId="3"><connectionPointIn><connection refLocalId="2" formalParameter="bRun"/>'
        '</connectionPointIn><expression>bMotor1</expression></outVariable>',
    )
    x = cross_reference(project)
    assert [_ld_row(r) for r in x.references if r.location.unit == P] == [
        (P, "1", "bStart1", "read", "v:GVL_IO.bStart1", "", None),
        (P, "1", "bStop1", "read", "v:GVL_IO.bStop1", "", None),
        (P, "2", "fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
        (P, "2", "bStart", "write", "v:PLC_PRG.fbConv1", "bStart", "v:FB_Motor.bStart"),
        (P, "2", "bRun", "read", "v:PLC_PRG.fbConv1", "bRun", "v:FB_Motor.bRun"),
        (P, "3", "bMotor1", "write", "v:GVL_IO.bMotor1", "", None),
    ]
    assert [u for u in x.unresolved if u.location.unit == P] == []


def test_ld_block_to_block_wiring():
    project = _ld_project(
        _in_out_project(),
        _block_xml(1, "fbConv1", _pin("outputVariables", "bRun"), _pin("inOutVariables", "io", ("2", "io"))),
        _block_xml(2, "fbConv2", _pin("inputVariables", "bInterlock", ("1", "bRun")), _pin("inOutVariables", "io", ("1", "io"))),
    )
    x = cross_reference(project)
    assert [_ld_row(r) for r in x.references if r.location.unit == P] == [
        (P, "1", "fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
        (P, "1", "bRun", "read", "v:PLC_PRG.fbConv1", "bRun", "v:FB_Motor.bRun"),
        (P, "1", "io", "readwrite", "v:PLC_PRG.fbConv1", "io", "v:FB_Motor.io"),
        (P, "2", "fbConv2", "call", "v:PLC_PRG.fbConv2", "", None),
        (P, "2", "bInterlock", "write", "v:PLC_PRG.fbConv2", "bInterlock", "v:FB_Motor.bInterlock"),
        (P, "2", "io", "readwrite", "v:PLC_PRG.fbConv2", "io", "v:FB_Motor.io"),
    ]
    assert [u for u in x.unresolved if u.location.unit == P] == []


@pytest.mark.parametrize("other_group", ["outputVariables", "inOutVariables"])
def test_ld_unknown_formal_merges_access_in_both_group_orders(other_group):
    """SYNTHETIC: an unresolved formal forces group fallback and exposes the merge itself."""
    for groups in (("inputVariables", other_group), (other_group, "inputVariables")):
        project = _ld_project(
            _in_out_project(),
            _block_xml(1, "fbConv1", *[
                _pin(group, "opaque", ("2", "io") if group != "outputVariables" else None)
                for group in groups
            ]),
            _block_xml(2, "fbConv2", _pin("inOutVariables", "io", ("1", "opaque"))),
        )
        x = cross_reference(project)
        assert [_ld_row(r) for r in x.references if r.location.unit == P] == [
            (P, "1", "fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
            (P, "1", "opaque", "readwrite", "v:PLC_PRG.fbConv1", "opaque", None),
            (P, "2", "fbConv2", "call", "v:PLC_PRG.fbConv2", "", None),
            (P, "2", "io", "readwrite", "v:PLC_PRG.fbConv2", "io", "v:FB_Motor.io"),
        ]
        assert [u for u in x.unresolved if u.location.unit == P] == []


def test_ld_fan_out_keeps_one_reference_per_pin():
    project = _ld_project(
        ET.parse(LARGE).getroot(),
        _block_xml(1, "fbConv1", _pin("outputVariables", "bRun")),
        _block_xml(2, "fbConv2", _pin("inputVariables", "bInterlock", ("1", "bRun"))),
        _block_xml(3, "fbConv3", _pin("inputVariables", "bInterlock", ("1", "bRun"))),
        '<outVariable localId="4"><connectionPointIn><connection refLocalId="1" formalParameter="bRun"/>'
        '</connectionPointIn><expression>bMotor1</expression></outVariable>',
    )
    x = cross_reference(project)
    rows = [_ld_row(r) for r in x.references if r.location.unit == P]
    assert len(rows) == 7
    assert rows.count((P, "1", "bRun", "read", "v:PLC_PRG.fbConv1", "bRun", "v:FB_Motor.bRun")) == 1
    assert [r for r in rows if r[3] == "call"] == [
        (P, "1", "fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
        (P, "2", "fbConv2", "call", "v:PLC_PRG.fbConv2", "", None),
        (P, "3", "fbConv3", "call", "v:PLC_PRG.fbConv3", "", None),
    ]
    assert [r for r in rows if r[2] == "bInterlock"] == [
        (P, "2", "bInterlock", "write", "v:PLC_PRG.fbConv2", "bInterlock", "v:FB_Motor.bInterlock"),
        (P, "3", "bInterlock", "write", "v:PLC_PRG.fbConv3", "bInterlock", "v:FB_Motor.bInterlock"),
    ]
    assert rows[-1] == (P, "4", "bMotor1", "write", "v:GVL_IO.bMotor1", "", None)


@pytest.mark.parametrize("marker_namespace", ["", NS["p"]], ids=["unqualified", "plcopen"])
@pytest.mark.parametrize("marker_text", ["execute", "Execute"])
def test_ld_execute_box_is_located_unresolved(marker_namespace, marker_text):
    """SYNTHETIC Execute marker in sample 03's actual vendorElement wrapper shape."""
    root = ET.parse(LARGE).getroot()
    template = root.find(".//p:LD/p:vendorElement", NS)
    execute = deepcopy(template)
    execute.set("localId", "90")
    marker = execute.find("p:addData/p:data/ElementType", NS)
    marker.tag = f"{{{marker_namespace}}}ElementType" if marker_namespace else "ElementType"
    marker.text = marker_text
    execute.find("p:alternativeText/" + XHTML, NS).text = "bMotor1 := TRUE;"
    unknown = deepcopy(template)
    unknown.set("localId", "91")
    unknown.find("p:addData/p:data/ElementType", NS).text = "other"
    foreign = deepcopy(execute)
    foreign.set("localId", "92")
    foreign.find("p:addData/p:data", NS)[0].tag = "{urn:vendor}ElementType"
    wrong_extension = deepcopy(execute)
    wrong_extension.set("localId", "93")
    wrong_extension.find("p:addData/p:data", NS).set("name", "urn:vendor:fbdelementtype")
    project = _ld_project(root, *[ET.tostring(e, encoding="unicode") for e in
                                 (template, execute, unknown, foreign, wrong_extension)],
                          '<contact localId="94"><variable>bDoorClosed</variable></contact>',
                          '<coil localId="95"><variable>bHorn</variable></coil>')
    before = deepcopy(project)
    x = cross_reference(project)
    assert [(u.text, u.access, u.reason, u.location.configuration, u.location.application,
             u.location.unit, u.location.local_id, u.location.line, u.location.column)
            for u in x.unresolved if u.location.unit == P] == [
        ("Execute", "call", "vendor element", "Device", "Application", P, "90", None, None),
    ]
    assert [_ld_row(r) for r in x.references if r.location.unit == P] == [
        (P, "94", "bDoorClosed", "read", "v:GVL_IO.bDoorClosed", "", None),
        (P, "95", "bHorn", "write", "v:GVL_IO.bHorn", "", None),
    ]
    assert project == before
    assert x.warnings == []


def test_ld_storage_and_negation_do_not_change_access():
    root = ET.parse(LARGE).getroot()
    root.find(".//p:LD/p:coil", NS).set("storage", "set")
    contact = root.find(".//p:LD/p:contact", NS)
    assert contact.get("negated") == "true"
    x = cross_reference(parse_element(root))
    assert [(r.text, r.access) for r in x.references if r.location.unit == "PRG_Alarm"] == [
        ("bDoorClosed", "read"), ("bHorn", "write"),
    ]


@pytest.mark.parametrize("constant_groups", [
    ["inOutVariables"], ["inputVariables", "inOutVariables"], ["inOutVariables", "inputVariables"],
])
def test_ld_pins_follow_the_shared_formal_direction_rule(constant_groups):
    """SYNTHETIC: resolved formals, including CONSTANT, determine pin access before merging."""
    project = _ld_project(
        _in_out_project(),
        _block_xml(1, "fbConv1", _pin("inputVariables", "bStart"), _pin("outputVariables", "bRun"),
                   _pin("inOutVariables", "io"), *[_pin(group, "ioc") for group in constant_groups]),
    )
    x = cross_reference(project)
    assert [_ld_row(r) for r in x.references if r.location.unit == P] == [
        (P, "1", "fbConv1", "call", "v:PLC_PRG.fbConv1", "", None),
        (P, "1", "bStart", "write", "v:PLC_PRG.fbConv1", "bStart", "v:FB_Motor.bStart"),
        (P, "1", "bRun", "read", "v:PLC_PRG.fbConv1", "bRun", "v:FB_Motor.bRun"),
        (P, "1", "io", "readwrite", "v:PLC_PRG.fbConv1", "io", "v:FB_Motor.io"),
        (P, "1", "ioc", "read", "v:PLC_PRG.fbConv1", "ioc", "v:FB_Motor.ioc"),
    ]
    assert [u for u in x.unresolved if u.location.unit == P] == []
