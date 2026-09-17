"""Command line interface: ``plcdoc parse FILE [--json]``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from plcdoc import __version__
from plcdoc.model import Project
from plcdoc.parser import ParseError, parse_file
from plcdoc.render import markdown_table
from plcdoc.tables import io_table, variable_table

IO_HEADERS = ("Address", "Direction", "Name", "Type", "Scope", "Comment")
VAR_HEADERS = ("Scope", "Section", "Name", "Type", "Address", "Initial", "Comment")


def render_report(project: Project) -> str:
    """Markdown report: project header, I/O table, variable list."""
    io_rows = io_table(project)
    variables = variable_table(project)
    parts = [
        f"# {project.name or '(unnamed project)'}",
        "",
        f"Product: {project.product_version or 'unknown'}",
        f"POUs: {', '.join(p.name for p in project.pous) or 'none'}",
        f"Global variable lists: {', '.join(g.name for g in project.gvls) or 'none'}",
        "",
        f"## I/O table ({len(io_rows)})",
        "",
        markdown_table(
            IO_HEADERS,
            [(r.address, r.direction, r.name, r.type, r.scope, r.comment) for r in io_rows],
        ),
        "",
        f"## Variables ({len(variables)})",
        "",
        markdown_table(
            VAR_HEADERS,
            [
                (v.scope, v.section, v.name, v.type, v.address, v.initial_value, v.comment)
                for v in variables
            ],
        ),
        "",
    ]
    return "\n".join(parts)


def render_json(project: Project) -> str:
    """Deterministic JSON: sorted keys, parse-order lists, UTF-8 text as-is."""
    return json.dumps(project.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plcdoc", description="Documentation and version diff for PLC projects."
    )
    parser.add_argument("--version", action="version", version=f"plcdoc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="print the I/O table and variable list of a file")
    p_parse.add_argument("file", help="PLCopen XML export")
    p_parse.add_argument(
        "--json", action="store_true", help="print the parsed project as JSON instead"
    )
    return parser


def _utf8_stdio() -> None:
    # Comments in real projects are not ASCII; Windows consoles default to a
    # legacy code page. Switch to UTF-8 where the stream supports it.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    if args.command == "parse":
        try:
            project = parse_file(args.file)
        except ParseError as exc:
            print(f"plcdoc: {exc}", file=sys.stderr)
            return 1
        for warning in project.warnings:
            print(f"plcdoc: warning: {warning}", file=sys.stderr)
        print(render_json(project) if args.json else render_report(project))
        return 0
    return 2  # unreachable: argparse enforces the subcommand


if __name__ == "__main__":
    sys.exit(main())
