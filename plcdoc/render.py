"""Text rendering helpers (Markdown tables)."""

from __future__ import annotations

from typing import Sequence


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """Render a padded Markdown table. Cells are stringified; None becomes empty."""
    text_rows = [[_cell(v) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in text_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    out = [line(list(headers)), "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    out.extend(line(row) for row in text_rows)
    return "\n".join(out)
