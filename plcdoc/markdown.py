"""GitHub Flavored Markdown export (Decision 008).

A renderer separate from the terminal report: each raw value is escaped once,
so that a table cell, heading or list item renders to its source text in any
GFM renderer (spec 0.29-gfm with the table, strikethrough and autolink
extensions). Internal: not part of ``plcdoc.__all__``.
"""

from __future__ import annotations

import re
import string
from typing import Sequence

from plcdoc.model import Project
from plcdoc.render import _layout
from plcdoc.tables import (
    IO_HEADERS,
    VAR_HEADERS,
    io_cells,
    io_table,
    variable_cells,
    variable_table,
)

_PUNCTUATION = frozenset(string.punctuation)
_LINE_ENDING = re.compile(r"\r\n|\r|\n")


def _edge(whitespace: str) -> str:
    return whitespace.replace(" ", "&#32;").replace("\t", "&#9;")


def escape(value: object) -> str:
    """Markdown source that renders to the text of *value*; None becomes empty.

    Three passes over the raw value. Passes 2 and 3 insert markup after pass 1,
    so inserted markup is never escaped again.
    """
    if value is None:
        return ""
    # 1. A backslash before every ASCII punctuation character (GFM 6.1).
    text = "".join("\\" + char if char in _PUNCTUATION else char for char in str(value))
    # 2. A line ending would end the row, heading or list item: <br> instead.
    text = _LINE_ENDING.sub("<br>", text)
    # 3. GFM trims spaces and tabs only at the edges of cells and headings.
    body = text.lstrip(" \t")
    core = body.rstrip(" \t")
    return _edge(text[: len(text) - len(body)]) + core + _edge(body[len(core):])


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """A GFM table; headers and cells are escaped, None becomes empty."""
    return _layout([escape(h) for h in headers], [[escape(v) for v in row] for row in rows])


def render_markdown(project: Project) -> str:
    """GFM report: title, metadata list, I/O table and variable list."""
    io_rows = io_table(project)
    variables = variable_table(project)
    lines = [
        "# " + escape(project.name or "(unnamed project)"),
        "",
        "- " + escape(f"Product: {project.product_version or 'unknown'}"),
        "- " + escape(f"POUs: {', '.join(p.name for p in project.pous) or 'none'}"),
        "- " + escape(
            f"Global variable lists: {', '.join(g.name for g in project.gvls) or 'none'}"
        ),
        "",
        "## " + escape(f"I/O table ({len(io_rows)})"),
        "",
        table(IO_HEADERS, [io_cells(r) for r in io_rows]),
        "",
        "## " + escape(f"Variables ({len(variables)})"),
        "",
        table(VAR_HEADERS, [variable_cells(v) for v in variables]),
    ]
    return "\n".join(lines) + "\n"
