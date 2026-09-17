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
    is_derived: bool = False  # True when the type came from type/derived (FB instance, user type)
    address: str | None = None  # "%IX0.0" or None when not mapped
    initial_value: str | None = None
    comment: str = ""  # stripped, "" when absent

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
class Pou:
    """A program organisation unit: program, functionBlock or function."""

    name: str
    pou_type: str
    return_type: str | None = None
    variables: list[Variable] = field(default_factory=list)
    body_language: str | None = None  # "ST", "LD", "FBD", ... or None when no body
    body_text: str | None = None  # textual body (LF line endings); None for graphical bodies


@dataclass
class GlobalVarList:
    name: str
    variables: list[Variable] = field(default_factory=list)


@dataclass
class Task:
    name: str
    interval: str | None = None
    priority: int | None = None
    programs: list[str] = field(default_factory=list)


@dataclass
class Project:
    name: str
    product_version: str
    pous: list[Pou] = field(default_factory=list)
    gvls: list[GlobalVarList] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
