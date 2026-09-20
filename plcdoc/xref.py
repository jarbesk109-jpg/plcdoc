"""Cross-reference: where each variable is read, written or called (Decision 011).

``cross_reference(project)`` is a pure function over the parse model. It scans
every code unit (POU body, action, method, property accessor), resolves each
identifier path against the declared scope and returns one :class:`Reference`
per resolved occurrence, plus the occurrences it could not resolve. Raw string
matching is never used: ``xOk`` in ``PLC_PRG`` and ``xOk`` in
``FB_Drive.M_Start`` are different targets, and ``E_DriveState.RUNNING`` is an
enum literal, not a variable.

The ST scanner is a tokenizer with a nesting-depth stack, not a parser. The
rules it needs are small: the path immediately before an assignment operator
is written, a path followed by ``(`` is called, ``IDENT :=`` / ``IDENT =>`` at
the start of a call argument names a formal parameter, and everything else is
read. See ``docs/decisions.md`` (011) for the complete rule set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator
from xml.etree import ElementTree as ET

from plcdoc.model import DataType, GlobalVarList, Method, Pou, Project, Variable

# --------------------------------------------------------------------------- #
# Public data model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Location:
    """Where an occurrence sits: which code unit, and line/column (ST) or local ID (LD)."""

    configuration: str | None
    application: str | None
    unit: str  # scope path: "PLC_PRG", "FB_Drive.M_Start", "FB_Drive.P_Speed.Get", ...
    line: int | None = None  # ST: 1-based line in body_text
    column: int | None = None  # ST: 1-based character column of the head identifier
    local_id: str | None = None  # LD: localId of the graphical element


@dataclass(frozen=True)
class Target:
    """A resolved declaration. For a variable this is ``Variable.identity`` plus ``kind``."""

    kind: str  # "variable" | "field" | "result" | "pou" | "method" | "property" | "action"
    configuration: str | None
    application: str | None
    scope: str  # declaring scope path (GVL, POU, "FB.Method", "FB.Prop.Get", DUT name)
    name: str  # declared spelling


@dataclass(frozen=True)
class Reference:
    """One resolved occurrence of a declaration in a code body."""

    target: Target  # the head of the access, e.g. variable PLC_PRG.fbDrive
    member: str  # "" or the dotted member path after the head ("eState", "M_Start.rTarget")
    member_target: Target | None  # declaration of the last member step when the types are known
    access: str  # "read" | "write" | "readwrite" | "call"
    location: Location
    text: str  # the path as written, without argument or index contents
    via: Target | None = None  # the VAR_EXTERNAL declaration the head was resolved through


@dataclass(frozen=True)
class Unresolved:
    text: str
    access: str
    location: Location
    reason: str


@dataclass
class CrossReference:
    references: list[Reference] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def cross_reference(project: Project) -> CrossReference:
    """Scan ST and supported graphical code units of *project*, returning references in scan order."""
    scanner = _Scanner(_Index(project))
    for unit in _units(project):
        if unit.body_language == "ST" and unit.body_text:
            scanner.scan_st(unit)
        elif unit.graphical_body:
            scanner.scan_graphical(unit)
    scanner.result.warnings = list(scanner.index.warnings)
    return scanner.result


def by_target(xref: CrossReference) -> dict[Target, list[Reference]]:
    """References grouped under their head target and, when present, their member target.

    A reference appears at most once per key, in scan order, so both "what does
    ``PLC_PRG`` do with ``fbDrive``" and "where is ``FB_Drive.xRunning`` read"
    can be answered from the same result.
    """
    grouped: dict[Target, list[Reference]] = {}
    for reference in xref.references:
        grouped.setdefault(reference.target, []).append(reference)
        if reference.member_target is not None and reference.member_target != reference.target:
            grouped.setdefault(reference.member_target, []).append(reference)
    return grouped


# --------------------------------------------------------------------------- #
# Code units
# --------------------------------------------------------------------------- #


@dataclass
class _Unit:
    path: str
    pou: Pou
    kind: str  # "pou" | "action" | "method" | "getter" | "setter"
    own_variables: list[Variable]
    result: str | None  # the unit's own name usable as a value, or None
    body_language: str | None
    body_text: str | None
    graphical_body: list

    @property
    def configuration(self) -> str | None:
        return self.pou.configuration

    @property
    def application(self) -> str | None:
        return self.pou.application


def _units(project: Project) -> Iterator[_Unit]:
    """POU body, then its actions, methods and properties (Get, then Set), in parse order."""
    for pou in project.pous:
        yield _Unit(
            pou.name, pou, "pou", [], pou.name if pou.pou_type == "function" else None,
            pou.body_language, pou.body_text, pou.graphical_body,
        )
        for action in pou.actions:
            yield _Unit(
                f"{pou.name}.{action.name}", pou, "action", [], None,
                action.body_language, action.body_text, action.graphical_body,
            )
        for method in pou.methods:
            yield _Unit(
                f"{pou.name}.{method.name}", pou, "method", method.variables, method.name,
                method.body_language, method.body_text, method.graphical_body,
            )
        for prop in pou.properties:
            for kind, accessor in (("Get", prop.getter), ("Set", prop.setter)):
                if accessor is not None:
                    yield _Unit(
                        f"{pou.name}.{prop.name}.{kind}", pou, kind.lower() + "ter",
                        accessor.variables, prop.name,
                        accessor.body_language, accessor.body_text, accessor.graphical_body,
                    )


# --------------------------------------------------------------------------- #
# Declaration index and scope resolution
# --------------------------------------------------------------------------- #

_Owner = tuple[str | None, str | None]


def _levels(configuration: str | None, application: str | None) -> list[_Owner]:
    """Owner chain: same application, then the configuration, then the project."""
    levels: list[_Owner] = [(configuration, application)]
    if application is not None:
        levels.append((configuration, None))
    if configuration is not None:
        levels.append((None, None))
    return levels


def _owner_text(owner: _Owner) -> str:
    return f"{owner[0] or '-'}/{owner[1] or '-'}"


@dataclass(frozen=True)
class _Head:
    """A resolved head: the target plus what is needed to continue into members."""

    target: Target
    decl: object  # Variable | Pou | Method | Property | Action
    owner: _Owner  # where the declaration lives; member lookups start from here
    via: Target | None = None


_ENUM_LITERAL = object()  # sentinel: the path is an enum literal, produce nothing


class _Index:
    """Name tables per owner, built once from the project."""

    def __init__(self, project: Project) -> None:
        self.pous: dict[_Owner, dict[str, list[Pou]]] = {}
        self.gvls: dict[_Owner, dict[str, list[GlobalVarList]]] = {}
        self.types: dict[_Owner, dict[str, list[DataType]]] = {}
        self.globals: dict[_Owner, dict[str, list[tuple[GlobalVarList, Variable]]]] = {}
        self.enum_values: dict[_Owner, set[str]] = {}
        self.warnings: dict[str, None] = {}
        self._type_cache: dict[int, ET.Element | None] = {}
        for pou in project.pous:
            self._add(self.pous, (pou.configuration, pou.application), pou.name, pou)
        for gvl in project.gvls:
            owner = (gvl.configuration, gvl.application)
            self._add(self.gvls, owner, gvl.name, gvl)
            for variable in gvl.variables:
                self._add(self.globals, owner, variable.name, (gvl, variable))
        for data_type in project.data_types:
            owner = (data_type.configuration, data_type.application)
            self._add(self.types, owner, data_type.name, data_type)
            self.enum_values.setdefault(owner, set()).update(v.name.lower() for v in data_type.values)

    @staticmethod
    def _add(table: dict, owner: _Owner, name: str, obj) -> None:
        table.setdefault(owner, {}).setdefault(name.lower(), []).append(obj)

    def warn(self, message: str) -> None:
        self.warnings.setdefault(message)

    def lookup(self, table: dict, owner: _Owner, name: str) -> list:
        """Candidates at the first owner level that declares *name*."""
        for level in _levels(*owner):
            found = table.get(level, {}).get(name.lower())
            if found:
                return found
        return []

    def pou(self, owner: _Owner, name: str) -> Pou | None:
        return self._first(self.lookup(self.pous, owner, name), "POU", name)

    def data_type(self, owner: _Owner, name: str) -> DataType | None:
        return self._first(self.lookup(self.types, owner, name), "data type", name)

    def gvl(self, owner: _Owner, name: str) -> GlobalVarList | None:
        return self._first(self.lookup(self.gvls, owner, name), "GVL", name)

    def _first(self, candidates: list, label: str, name: str):
        if not candidates:
            return None
        if len(candidates) > 1:
            first = candidates[0]
            self.warn(
                f"ambiguous {label} {first.name!r} in "
                f"{_owner_text((first.configuration, first.application))}: using the first definition"
            )
        return candidates[0]

    def global_variable(self, owner: _Owner, name: str) -> tuple[GlobalVarList, Variable] | None:
        candidates = self.lookup(self.globals, owner, name)
        if not candidates:
            return None
        if len(candidates) > 1:
            names = ", ".join(gvl.name for gvl, _ in candidates)
            self.warn(
                f"ambiguous global {candidates[0][1].name!r}: {names} (using {candidates[0][0].name})"
            )
        return candidates[0]

    def is_enum_value(self, owner: _Owner, name: str) -> bool:
        return any(name.lower() in self.enum_values.get(level, ()) for level in _levels(*owner))

    def type_element(self, variable: Variable) -> ET.Element | None:
        """The parsed ``<type>`` of a declaration (cached; ``None`` when absent)."""
        key = id(variable)
        if key not in self._type_cache:
            self._type_cache[key] = (
                ET.fromstring(variable.type_xml) if variable.type_xml else None
            )
        return self._type_cache[key]


def _variable_target(variable: Variable, kind: str = "variable") -> Target:
    return Target(kind, variable.configuration, variable.application, variable.scope, variable.name)


def _member_of_pou(pou: Pou, name: str) -> tuple[Target, object] | None:
    """A POU's variable, method, property or action by name -> (target, declaration)."""
    key = name.lower()
    for variable in pou.variables:
        if variable.name.lower() == key:
            return _variable_target(variable), variable
    owner = (pou.configuration, pou.application)
    for method in pou.methods:
        if method.name.lower() == key:
            return Target("method", *owner, pou.name, method.name), method
    for prop in pou.properties:
        if prop.name.lower() == key:
            return Target("property", *owner, pou.name, prop.name), prop
    for action in pou.actions:
        if action.name.lower() == key:
            return Target("action", *owner, pou.name, action.name), action
    return None


def _split_tag(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return "", tag


# --------------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------------- #

_KEYWORDS = frozenset("""
IF THEN ELSE ELSIF END_IF CASE OF END_CASE FOR TO BY DO END_FOR WHILE END_WHILE REPEAT UNTIL
END_REPEAT RETURN EXIT CONTINUE AND OR XOR NOT MOD AND_THEN OR_ELSE TRUE FALSE NULL
VAR VAR_INPUT VAR_OUTPUT VAR_IN_OUT VAR_TEMP VAR_STAT VAR_EXTERNAL END_VAR CONSTANT RETAIN
PERSISTENT
""".split())
_SELF = frozenset({"THIS", "SUPER"})
_ASSIGN = frozenset({":=", "S=", "R=", "REF="})

_TOKEN_RE = re.compile(
    r"""
    (?P<skip>\s+|//[^\n]*|\(\*.*?\*\)|/\*.*?\*/|\{[^}]*\}
        |'(?:\$.|[^'$])*'|"(?:\$.|[^"$])*")
  | (?P<literal>%[A-Za-z]+[0-9.]*
        |[A-Za-z_][A-Za-z0-9_]*\#[A-Za-z0-9_.:+\-]*
        |[0-9][0-9_]*\#[0-9A-Fa-f_]+
        |[0-9][0-9_]*(?:\.[0-9][0-9_]*)?(?:[eE][+-]?[0-9]+)?)
  | (?P<assign>(?i:REF=|S=|R=)|:=)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>=>|<=|>=|<>|\*\*|[-+*/<>=^.(),;:\[\]])
  | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass(frozen=True)
class _Token:
    kind: str  # "ident" | "keyword" | "self" | "literal" | "assign" | "op" | "other"
    text: str
    offset: int


def _tokenize(text: str) -> list[_Token]:
    tokens = []
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup
        if kind == "skip":
            continue
        value = match.group()
        if kind == "ident":
            upper = value.upper()
            if upper in _SELF:
                kind = "self"
            elif upper in _KEYWORDS:
                kind = "keyword"
        elif kind == "assign":
            value = value.upper()
        tokens.append(_Token(kind, value, match.start()))
    return tokens


# --------------------------------------------------------------------------- #
# Paths and the scanner
# --------------------------------------------------------------------------- #


@dataclass
class _Path:
    segments: list[_Token]  # head first; "self" or "ident" tokens
    text: str  # as written, without index contents
    end: int  # index of the first token after the path
    index_ranges: list[tuple[int, int]] = field(default_factory=list)  # token ranges inside [ ]

    @property
    def head(self) -> _Token:
        return self.segments[0]


@dataclass
class _Frame:
    """An open ``(`` (call or grouping) or ``[``."""

    opener: str
    callee: _Callee | None = None  # set for a call frame
    arg_start: bool = True
    arg_index: int = 0
    pending_actual: str | None = None  # access for the actual after "IDENT :=" / "IDENT =>"


@dataclass
class _Callee:
    target: Target | None  # None for an unresolved callee
    member: str
    via: Target | None
    formals: list[Variable] | None  # interface parameters in declaration order, when known


_DIRECTION = {  # section -> (formal access, actual access)
    "input": ("write", "read"),
    "output": ("read", "write"),
    "inout": ("readwrite", "readwrite"),
}
# LD/FBD groups supply the direction only when the formal declaration is unavailable.
_PIN_SECTION_BY_GROUP = {"inputVariables": "input", "outputVariables": "output", "inOutVariables": "inout"}
_PIN_ACCESS_BY_ELEMENT = {"inVariable": "read", "outVariable": "write", "inOutVariable": "readwrite"}


def _expression_text(xml: str) -> str | None:
    """The ``expression`` text of an inVariable/outVariable/inOutVariable element."""
    element = ET.fromstring(xml)
    for child in element:
        if isinstance(child.tag, str) and _split_tag(child.tag)[1] == "expression":
            return "".join(child.itertext())
    return None


def _direction(formal: Variable | None, fallback_section: str = "input") -> tuple[str, str]:
    """Parameter direction rule (Decision 011)."""
    if formal is None:
        return _DIRECTION[fallback_section]
    if formal.section == "inout" and formal.constant:
        return ("read", "read")
    return _DIRECTION.get(formal.section, ("read", "read"))


class _Scanner:
    def __init__(self, index: _Index) -> None:
        self.index = index
        self.result = CrossReference()
        self._fixed_location: Location | None = None  # set while scanning a graphical element

    # -- ST ----------------------------------------------------------------- #

    def scan_st(self, unit: _Unit) -> None:
        self._unit = unit
        self._text = unit.body_text or ""
        self._fixed_location = None
        tokens = _tokenize(self._text)
        self._scan(tokens, 0, len(tokens), [])

    def _location(self, offset: int) -> Location:
        if self._fixed_location is not None:
            return self._fixed_location
        line_start = self._text.rfind("\n", 0, offset) + 1
        return Location(
            self._unit.configuration, self._unit.application, self._unit.path,
            line=self._text.count("\n", 0, offset) + 1, column=offset - line_start + 1,
        )

    # -- LD / graphical ------------------------------------------------------ #

    def scan_graphical(self, unit: _Unit) -> None:
        """Contacts read, coils write, in/out variables read/write, blocks call plus one reference per pin."""
        self._unit = unit
        self._text = ""
        for element in unit.graphical_body:
            self._fixed_location = Location(
                unit.configuration, unit.application, unit.path, local_id=element.local_id,
            )
            if element.kind == "contact":
                self._graphical_expression(element.variable, "read")
            elif element.kind == "coil":
                self._graphical_expression(element.variable, "write")
            elif element.kind in _PIN_ACCESS_BY_ELEMENT:
                self._graphical_expression(
                    _expression_text(element.xml), _PIN_ACCESS_BY_ELEMENT[element.kind],
                )
            elif element.kind == "block":
                self._block(element.xml)
        self._fixed_location = None

    def _graphical_expression(self, text: str | None, access: str) -> None:
        """A bare path gets *access*; any other expression is scanned as reads."""
        if not text or not text.strip():
            return
        tokens = _tokenize(text)
        if not tokens:
            return
        if tokens[0].kind in ("ident", "self"):
            path = self._path(tokens, 0, len(tokens))
            if path.end == len(tokens):
                self._emit(path, access)
                self._scan_indexes(tokens, path)
                return
        self._scan(tokens, 0, len(tokens), [])

    def _block(self, xml: str) -> None:
        block = ET.fromstring(xml)
        callee_text = block.get("instanceName") or block.get("typeName") or ""
        callee: _Callee | None = None
        tokens = _tokenize(callee_text)
        if tokens and tokens[0].kind in ("ident", "self"):
            path = self._path(tokens, 0, len(tokens))
            if path.end == len(tokens):
                callee = self._emit(path, "call")
        if callee is None:
            return  # nothing to attach pins to (no name, or an enum literal)
        # Exactly one reference per pin; a pin listed under several groups merges to readwrite.
        formals = {v.name.lower(): v for v in callee.formals or []}
        pins: dict[str, str] = {}
        for group in block:
            if not isinstance(group.tag, str):
                continue
            section = _PIN_SECTION_BY_GROUP.get(_split_tag(group.tag)[1])
            if section is None:
                continue
            for pin in group:
                if not isinstance(pin.tag, str) or _split_tag(pin.tag)[1] != "variable":
                    continue
                name = pin.get("formalParameter", "")
                if not name:
                    continue
                direction = _direction(formals.get(name.lower()), section)[0]
                previous = pins.get(name)
                pins[name] = direction if previous in (None, direction) else "readwrite"
        for name, access in pins.items():
            location = self._location(0)
            if callee.target is None:
                self.result.unresolved.append(Unresolved(name, access, location, "undeclared callee"))
                continue
            formal = formals.get(name.lower())
            member = f"{callee.member}.{name}" if callee.member else name
            self.result.references.append(Reference(
                callee.target, member, _variable_target(formal) if formal is not None else None,
                access, location, name, callee.via,
            ))

    def _scan(self, tokens: list[_Token], start: int, end: int, stack: list[_Frame]) -> None:
        i = start
        while i < end:
            token = tokens[i]
            frame = stack[-1] if stack else None
            if token.kind in ("ident", "self"):
                path = self._path(tokens, i, end)
                following = tokens[path.end] if path.end < end else None
                # A bare argument is a path that is the whole actual: "fb(x, y)".
                bare = following is None or following.text in (",", ")")
                named_formal = (
                    frame is not None and frame.callee is not None and frame.arg_start
                    and following is not None and following.text in (":=", "=>")
                )
                if named_formal:
                    self._formal(frame, path, following.text)
                    i = path.end + 1
                elif following is not None and following.kind == "assign":
                    self._emit(path, "write")
                    i = path.end + 1
                elif following is not None and following.text == "(":
                    callee = self._emit(path, "call")
                    self._scan_indexes(tokens, path)
                    stack.append(_Frame("(", callee=callee))
                    i = path.end + 1
                    if frame is not None:
                        frame.arg_start = False
                        frame.pending_actual = None
                    continue
                else:
                    access = "read"
                    if frame is not None and frame.callee is not None and bare:
                        if frame.pending_actual is not None:
                            access = frame.pending_actual
                        elif frame.arg_start:
                            formals = frame.callee.formals
                            if formals is not None and frame.arg_index < len(formals):
                                access = _direction(formals[frame.arg_index])[1]
                    self._emit(path, access)
                    i = path.end
                # Index contents come after the head in scan order: "a[i]" emits a, then i.
                self._scan_indexes(tokens, path)
                if frame is not None:
                    frame.arg_start = False
                    if not named_formal:
                        frame.pending_actual = None
                continue
            if token.text in ("(", "["):
                stack.append(_Frame(token.text))
            elif token.text in (")", "]"):
                if stack:
                    stack.pop()
            elif token.text == "," and frame is not None:
                frame.arg_start = True
                frame.arg_index += 1
                frame.pending_actual = None
                i += 1
                continue
            if frame is not None and token.text not in ("(", "["):
                frame.arg_start = False
                frame.pending_actual = None
            i += 1

    def _path(self, tokens: list[_Token], i: int, end: int) -> _Path:
        """Collect ``IDENT ("." IDENT | "^" | "[" ... "]")*`` starting at *i*."""
        segments = [tokens[i]]
        text = tokens[i].text
        ranges = []
        i += 1
        while i < end:
            token = tokens[i]
            if token.text == "^":
                text += "^"
                i += 1
            elif token.text == "." and i + 1 < end and tokens[i + 1].kind == "ident":
                segments.append(tokens[i + 1])
                text += "." + tokens[i + 1].text
                i += 2
            elif token.text == "." and i + 1 < end and tokens[i + 1].kind == "literal":
                i += 2  # bit access: the path ends before the number
                break
            elif token.text == "[":
                close = self._matching(tokens, i, end)
                ranges.append((i + 1, close))
                i = close + 1
            else:
                break
        return _Path(segments, text, i, ranges)

    def _scan_indexes(self, tokens: list[_Token], path: _Path) -> None:
        """Index expressions are plain expressions: every identifier inside is read."""
        for start, stop in path.index_ranges:
            self._scan(tokens, start, stop, [])

    @staticmethod
    def _matching(tokens: list[_Token], i: int, end: int) -> int:
        depth = 0
        for j in range(i, end):
            if tokens[j].text == "[":
                depth += 1
            elif tokens[j].text == "]":
                depth -= 1
                if depth == 0:
                    return j
        return end

    # -- emitting ------------------------------------------------------------ #

    def _emit(self, path: _Path, access: str) -> _Callee | None:
        """Resolve *path* and record a Reference or an Unresolved; return callee info for calls."""
        location = self._location(path.head.offset)
        resolved = self._resolve(path, is_call=(access == "call"))
        if resolved is _ENUM_LITERAL:
            return None
        if isinstance(resolved, str):
            self.result.unresolved.append(Unresolved(path.text, access, location, resolved))
            return _Callee(None, "", None, None) if access == "call" else None
        head, member, member_target, last_decl = resolved
        self.result.references.append(Reference(
            head.target, member, member_target, access, location, path.text, head.via,
        ))
        if access == "call":
            return _Callee(head.target, member, head.via, self._formals(last_decl, head.owner))
        return None

    def _formal(self, frame: _Frame, path: _Path, operator: str) -> None:
        """``IDENT :=`` / ``IDENT =>`` at argument start names a formal parameter of the callee."""
        callee = frame.callee
        assert callee is not None
        name = path.text
        location = self._location(path.head.offset)
        formal = None
        if callee.formals is not None:
            formal = next((v for v in callee.formals if v.name.lower() == name.lower()), None)
        formal_access, actual_access = _direction(formal, "output" if operator == "=>" else "input")
        frame.pending_actual = actual_access
        if callee.target is None:
            self.result.unresolved.append(Unresolved(name, formal_access, location, "undeclared callee"))
            return
        member = f"{callee.member}.{name}" if callee.member else name
        self.result.references.append(Reference(
            callee.target, member, _variable_target(formal) if formal is not None else None,
            formal_access, location, name, callee.via,
        ))

    def _formals(self, decl: object, owner: _Owner) -> list[Variable] | None:
        """Interface parameters (input, inout, output; declaration order) of a callable declaration."""
        if isinstance(decl, Variable):
            decl = self._derived(decl, owner)
        if isinstance(decl, (Pou, Method)):
            return [v for v in decl.variables if v.section in ("input", "inout", "output")]
        return None

    # -- resolution ---------------------------------------------------------- #

    def _resolve(self, path: _Path, is_call: bool):
        """-> (head, member, member_target, last_decl) | reason string | _ENUM_LITERAL."""
        segments = path.segments
        unit = self._unit
        owner = (unit.configuration, unit.application)
        first = segments[0]
        if first.kind == "self":
            if first.text.upper() == "SUPER":
                return "inheritance"
            if len(segments) == 1:
                return "this without member"
            found = _member_of_pou(unit.pou, segments[1].text)
            if found is None:
                return "no such member"
            head = self._normalise(found, owner)
            if isinstance(head, str):
                return head
            return self._members(head, segments[2:])

        name = first.text
        key = name.lower()
        # 1. the unit's own variables
        for variable in unit.own_variables:
            if variable.name.lower() == key:
                return self._members(_Head(_variable_target(variable), variable, owner), segments[1:])
        # 2. the unit's result symbol (not when called)
        if unit.result is not None and unit.result.lower() == key and not is_call:
            target = Target("result", *owner, unit.path, unit.result)
            return _Head(target, None, owner), "", None, None
        # 3./4. the owning POU's variables, then its methods/properties/actions
        found = _member_of_pou(unit.pou, name)
        if found is not None:
            head = self._normalise(found, owner)
            if isinstance(head, str):
                return head
            return self._members(head, segments[1:])
        # 6. globals through the owner chain
        found_global = self.index.global_variable(owner, name)
        if found_global is not None:
            _, variable = found_global
            head = _Head(_variable_target(variable), variable, (variable.configuration, variable.application))
            return self._members(head, segments[1:])
        # 7. POU, GVL and DUT names
        pou = self.index.pou(owner, name)
        if pou is not None:
            pou_owner = (pou.configuration, pou.application)
            if len(segments) == 1:
                return _Head(Target("pou", *pou_owner, pou.name, pou.name), pou, pou_owner), "", None, pou
            found = _member_of_pou(pou, segments[1].text)
            if found is None:
                return "no such member"
            head = self._normalise(found, pou_owner)
            if isinstance(head, str):
                return head
            return self._members(head, segments[2:])
        gvl = self.index.gvl(owner, name)
        if gvl is not None:
            if len(segments) == 1:
                return "no such global"
            variable = next((v for v in gvl.variables if v.name.lower() == segments[1].text.lower()), None)
            if variable is None:
                return "no such global"
            head = _Head(_variable_target(variable), variable, (gvl.configuration, gvl.application))
            return self._members(head, segments[2:])
        data_type = self.index.data_type(owner, name)
        if data_type is not None:
            if data_type.kind == "enum" and len(segments) == 2 and any(
                v.name.lower() == segments[1].text.lower() for v in data_type.values
            ):
                return _ENUM_LITERAL
            return "type used as value"
        # 8. unqualified enum literal
        if len(segments) == 1 and self.index.is_enum_value(owner, name):
            return _ENUM_LITERAL
        return "undeclared"

    def _normalise(self, found: tuple[Target, object], owner: _Owner):
        """Alias normalisation: a VAR_EXTERNAL declaration stands for the visible global."""
        target, decl = found
        if isinstance(decl, Variable) and decl.section == "external":
            found_global = self.index.global_variable(owner, decl.name)
            if found_global is None:
                return "external without global"
            _, variable = found_global
            return _Head(
                _variable_target(variable), variable,
                (variable.configuration, variable.application), via=target,
            )
        return _Head(target, decl, owner)

    def _members(self, head: _Head, rest: list[_Token]):
        """Walk the member path after the head through the declared types."""
        member = ".".join(token.text for token in rest)
        if not rest:
            return head, "", None, head.decl
        member_target: Target | None = None
        decl: object = head.decl
        type_elem = self.index.type_element(decl) if isinstance(decl, Variable) else None
        owner = head.owner
        for token in rest:
            if isinstance(decl, Pou):
                found = _member_of_pou(decl, token.text)
                normalised = self._normalise(found, owner) if found is not None else "no such member"
                if isinstance(normalised, str):
                    member_target, decl, type_elem = None, None, None
                else:
                    member_target, decl, owner = normalised.target, normalised.decl, normalised.owner
                    type_elem = self.index.type_element(decl) if isinstance(decl, Variable) else None
            elif isinstance(decl, (Variable, _InlineField)):
                member_target, decl, type_elem, owner = self._step_type(type_elem, owner, token.text)
            else:
                member_target, decl, type_elem = None, None, None
        return head, member, member_target, decl

    def _step_type(self, type_elem: ET.Element | None, owner: _Owner, name: str):
        """One member step through a ``<type>`` (or ``<baseType>``) element."""
        if type_elem is None:
            return None, None, None, owner
        children = [child for child in type_elem if isinstance(child.tag, str)]
        if len(children) != 1:
            return None, None, None, owner
        child = children[0]
        namespace, local = _split_tag(child.tag)
        if local == "derived":
            declared = child.get("name", "")
            pou = self.index.pou(owner, declared)
            if pou is not None:
                found = _member_of_pou(pou, name)
                if found is None:
                    return None, None, None, owner
                normalised = self._normalise(found, (pou.configuration, pou.application))
                if isinstance(normalised, str):
                    return None, None, None, owner
                decl = normalised.decl
                next_type = self.index.type_element(decl) if isinstance(decl, Variable) else None
                return normalised.target, decl, next_type, normalised.owner
            data_type = self.index.data_type(owner, declared)
            if data_type is not None and data_type.kind == "struct":
                for member in data_type.members:
                    if member.name.lower() == name.lower():
                        return (
                            _variable_target(member, "field"), member,
                            self.index.type_element(member), (member.configuration, member.application),
                        )
            return None, None, None, owner
        if local == "array":
            base = next((c for c in child if isinstance(c.tag, str) and _split_tag(c.tag)[1] == "baseType"), None)
            return self._step_type(base, owner, name)
        if local == "struct":
            for variable in child:
                if isinstance(variable.tag, str) and _split_tag(variable.tag)[1] == "variable" \
                        and variable.get("name", "").lower() == name.lower():
                    field_type = next(
                        (c for c in variable if isinstance(c.tag, str) and _split_tag(c.tag)[1] == "type"), None,
                    )
                    return None, _InlineField(), field_type, owner
            return None, None, None, owner
        return None, None, None, owner  # pointer, elementary, string, unknown: stop

    def _derived(self, variable: Variable, owner: _Owner) -> Pou | None:
        """The POU a variable is an instance of (through arrays), or None."""
        type_elem = self.index.type_element(variable)
        while type_elem is not None:
            children = [child for child in type_elem if isinstance(child.tag, str)]
            if len(children) != 1:
                return None
            child = children[0]
            local = _split_tag(child.tag)[1]
            if local == "derived":
                return self.index.pou(owner, child.get("name", ""))
            if local == "array":
                type_elem = next(
                    (c for c in child if isinstance(c.tag, str) and _split_tag(c.tag)[1] == "baseType"), None,
                )
                continue
            return None
        return None


class _InlineField:
    """Marker declaration for a field of an anonymous struct: the walk continues, no target."""
