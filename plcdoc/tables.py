"""Derived tables from a :class:`Project`: I/O table and variable list."""

from __future__ import annotations

from dataclasses import dataclass

from plcdoc.model import Project, Variable


@dataclass
class IoRow:
    address: str
    direction: str  # "input", "output", "memory" or "" when the address is unparseable
    name: str
    type: str
    scope: str
    comment: str


def _io_sort_key(var: Variable) -> tuple:
    parsed = var.parsed_address
    if parsed is None:
        # Unparseable addresses go last, in plain string order.
        return (1, var.address or "", var.scope, var.name)
    return (0, parsed.sort_key, var.scope, var.name)


def io_table(project: Project) -> list[IoRow]:
    """All addressed variables in natural address order (I, Q, M; X, B, W, D, L; byte.bit)."""
    rows = []
    for var in sorted(project.io_variables(), key=_io_sort_key):
        rows.append(
            IoRow(
                address=var.address or "",
                direction=var.direction or "",
                name=var.name,
                type=var.type,
                scope=var.scope,
                comment=var.comment,
            )
        )
    return rows


def variable_table(project: Project) -> list[Variable]:
    """Every variable in parse order: global lists first, then POUs."""
    return list(project.all_variables())
