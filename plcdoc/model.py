"""Data model for a parsed PLCopen project.

Plain dataclasses only. Nothing here references the XML tree; the parser
fills these objects and every other module works from them.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

# Accepts %IX0.0, %QW10, %MD4, %I0.0 (size omitted = bit) and hierarchical %IX1.2.3
_ADDRESS_RE = re.compile(r"^%([IQM])([XBWDL]?)(\d+(?:\.\d+)*)$", re.IGNORECASE)

_AREA_ORDER = {"I": 0, "Q": 1, "M": 2}
_SIZE_ORDER = {"X": 0, "B": 1, "W": 2, "D": 3, "L": 4}

DIRECTION_BY_AREA = {"I": "input", "Q": "output", "M": "memory"}


@dataclass(frozen=True)
class Address:
    """A parsed IEC 61131-3 direct address such as ``%IX0.7`` or ``%QW10``.

    ``path`` holds the numeric parts: ``(0, 7)`` for ``%IX0.7``, ``(10,)`` for
    ``%QW10``. Tuples compare element by element, so ``%IX0.10`` sorts after
    ``%IX0.2`` and ``%IX1.0`` sorts after ``%IX0.7``.
    """

    area: str  # I, Q or M
    size: str  # X, B, W, D or L
    path: tuple[int, ...]

    @property
    def byte(self) -> int:
        return self.path[0]

    @property
    def bit(self) -> int | None:
        return self.path[1] if len(self.path) > 1 else None

    @property
    def direction(self) -> str:
        return DIRECTION_BY_AREA[self.area]

    @property
    def sort_key(self) -> tuple[int, int, tuple[int, ...]]:
        """Natural order: area (I, Q, M), then size (X, B, W, D, L), then byte.bit."""
        return (_AREA_ORDER[self.area], _SIZE_ORDER[self.size], self.path)


def parse_address(text: str) -> Address:
    """Parse ``%IX0.0``-style text into an :class:`Address`.

    Raises ``ValueError`` when the text is not a direct address.
    The size letter may be omitted (``%I0.0``), which IEC treats as a bit (``X``).
    """
    match = _ADDRESS_RE.match(text.strip())
    if not match:
        raise ValueError(f"not an IEC direct address: {text!r}")
    area, size, numbers = match.groups()
    return Address(
        area=area.upper(),
        size=(size or "X").upper(),
        path=tuple(int(n) for n in numbers.split(".")),
    )


@dataclass
class Variable:
    """One declared variable, wherever it was declared."""

    name: str
    type: str  # "BOOL", "INT", "CTU", "FB_Motor", ...
    scope: str  # owning POU or global variable list, e.g. "PLC_PRG", "GVL_IO"
    section: str  # "local", "input", "output", "inout", "temp", "external", "global", ...
    address: str | None = None  # "%IX0.0" or None when not mapped
    initial_value: str | None = None  # readable value, or "(array)" / "(struct)" / "(unknown)"
    comment: str = ""  # stripped, "" when absent
    configuration: str | None = None
    application: str | None = None  # resource name; None for project/configuration declarations
    retain: bool = False
    nonretain: bool = False
    persistent: bool = False
    constant: bool = False
    # Canonical XML keeps details that the readable type/value may not express.
    type_xml: str | None = None
    initial_value_xml: str | None = None
    derived_types: list[str] = field(default_factory=list)  # derived bases, also inside arrays

    @property
    def identity(self) -> tuple[str | None, str | None, str, str]:
        """Project-wide variable key: (configuration, application, scope, name)."""
        return (self.configuration, self.application, self.scope, self.name)

    @property
    def parsed_address(self) -> Address | None:
        if self.address is None:
            return None
        try:
            return parse_address(self.address)
        except ValueError:
            return None

    @property
    def direction(self) -> str | None:
        """``input``, ``output`` or ``memory`` from the address prefix, else None."""
        parsed = self.parsed_address
        return parsed.direction if parsed else None


@dataclass
class GraphicalElement:
    """One graphical instruction, plus canonical XML for unmodelled details."""

    kind: str
    local_id: str | None = None
    variable: str | None = None
    negated: bool | None = None
    storage: str | None = None
    edge: str | None = None
    incoming_ref_local_ids: list[str] = field(default_factory=list)
    xml: str = ""


@dataclass
class Pou:
    """A program organisation unit: program, functionBlock or function."""

    name: str
    pou_type: str
    return_type: str | None = None
    variables: list[Variable] = field(default_factory=list)
    body_language: str | None = None  # "ST", "LD", "FBD", ... or None when no body
    body_text: str | None = None  # textual body (LF line endings); None for graphical bodies
    configuration: str | None = None
    application: str | None = None
    comment: str = ""  # POU documentation, stripped, "" when absent
    return_type_xml: str | None = None
    graphical_body: list[GraphicalElement] = field(default_factory=list)
    body_xml: str | None = None  # canonical graphical body, including vendor/FBD/CFC details


@dataclass
class GlobalVarList:
    name: str
    variables: list[Variable] = field(default_factory=list)
    configuration: str | None = None
    application: str | None = None


@dataclass(frozen=True)
class Attribute:
    """A CODESYS ``{attribute '...'}`` pragma, in declaration order."""

    name: str
    value: str  # "" for a flag pragma such as {attribute 'qualified_only'}


@dataclass(frozen=True)
class EnumValue:
    name: str
    value: str | None  # explicit value text ("0", "10"); None when the export has none


@dataclass
class DataType:
    """A user data type (DUT): STRUCT, ENUM or another base type."""

    name: str
    kind: str  # "struct" | "enum" | "other"
    base_type: str | None = None  # enum: enum/baseType when exported (CODESYS omits it), else None
    base_type_xml: str | None = None  # canonical <baseType>, always kept
    members: list[Variable] = field(default_factory=list)  # struct fields: scope = DUT name, section "struct"
    values: list[EnumValue] = field(default_factory=list)  # enum values
    attributes: list[Attribute] = field(default_factory=list)
    comment: str = ""
    configuration: str | None = None
    application: str | None = None
    vendor_xml: list[str] = field(default_factory=list)  # unmodelled addData and unexpected children


@dataclass(frozen=True)
class PouInstance:
    instance_name: str
    type_name: str  # falls back to instance_name when CODESYS leaves typeName empty


@dataclass
class Task:
    name: str
    interval: str | None = None
    priority: int | None = None
    programs: list[PouInstance] = field(default_factory=list)
    configuration: str | None = None
    application: str | None = None
    settings: dict[str, str] = field(default_factory=dict)  # CODESYS TaskSettings, flattened


@dataclass
class Project:
    name: str
    product_version: str
    pous: list[Pou] = field(default_factory=list)
    gvls: list[GlobalVarList] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_types: list[DataType] = field(default_factory=list)

    def all_variables(self) -> Iterator[Variable]:
        """Every variable: global variable lists first, then POUs, in parse order."""
        for gvl in self.gvls:
            yield from gvl.variables
        for pou in self.pous:
            yield from pou.variables

    def io_variables(self) -> Iterator[Variable]:
        """Variables that carry a direct address."""
        return (v for v in self.all_variables() if v.address is not None)

    def to_dict(self) -> dict[str, Any]:
        """Plain dict, JSON-ready. Key order follows field order; lists keep parse order."""
        return asdict(self)
