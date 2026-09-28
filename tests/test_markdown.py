"""Markdown export (Decision 008): escaping, report layout and sample output.

Markdown is rendered with cmark-gfm and compared as text content: entities
decoded once, <br> read as a line feed, nothing stripped. Expected values come
from the model attributes, never from the export's own cell projections.
"""

import string
from html.parser import HTMLParser
from pathlib import Path

import cmarkgfm
import pytest
from cmarkgfm.cmark import Options

from plcdoc import Project, parse_file
from plcdoc.markdown import escape, render_markdown, table
from plcdoc.tables import io_table

from conftest import SAMPLES

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "markdown"
SAMPLE_FILES = sorted(SAMPLES.glob("*.xml"))


def _render(markdown):
    return cmarkgfm.markdown_to_html_with_extensions(
        markdown,
        options=Options.CMARK_OPT_UNSAFE,
        extensions=["table", "autolink", "strikethrough", "tagfilter"],
    )


class _Blocks(HTMLParser):
    """h1/h2/li texts and tables (rows of cell texts) in document order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._text = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "li", "th", "td"):
            self._text = []
        elif tag == "table":
            self.blocks.append(("table", []))
        elif tag == "tr":
            self.blocks[-1][1].append([])
        elif tag == "br" and self._text is not None:
            self._text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "li"):
            self.blocks.append((tag, "".join(self._text)))
            self._text = None
        elif tag in ("th", "td"):
            self.blocks[-1][1][-1].append("".join(self._text))
            self._text = None

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)


def _blocks(markdown):
    parser = _Blocks()
    parser.feed(_render(markdown))
    parser.close()
    return parser.blocks


def _text(value):
    """Rendered text of a raw value: only the kind of line ending changes."""
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


# The escaping spec of M3b step 4: value, Markdown source, rendered text.
CELL_CASES = [
    pytest.param('a|b', 'a\\|b', 'a|b', id="pipe"),
    pytest.param('C:\\tmp', 'C\\:\\\\tmp', 'C:\\tmp', id="backslash"),
    pytest.param('x\\|y', 'x\\\\\\|y', 'x\\|y', id="bs-pipe"),
    pytest.param('a`b`', 'a\\`b\\`', 'a`b`', id="backtick"),
    pytest.param('*x*', '\\*x\\*', '*x*', id="star"),
    pytest.param('_x_ FB_Motor', '\\_x\\_ FB\\_Motor', '_x_ FB_Motor', id="underscore"),
    pytest.param('<b>', '\\<b\\>', '<b>', id="lt-html"),
    pytest.param('<3@example.com>', '\\<3\\@example\\.com\\>', '<3@example.com>', id="autolink"),
    pytest.param('&#65; &copy;', '\\&\\#65\\; \\&copy\\;', '&#65; &copy;', id="entity"),
    pytest.param('\\<b>', '\\\\\\<b\\>', '\\<b>', id="html-bs"),
    pytest.param('a\nb', 'a<br>b', 'a\nb', id="newline"),
    pytest.param('a\rb', 'a<br>b', 'a\nb', id="cr"),
    pytest.param('a\r\nb', 'a<br>b', 'a\nb', id="crlf"),
    pytest.param('a\tb', 'a\tb', 'a\tb', id="tab"),
    pytest.param('  x  ', '&#32;&#32;x&#32;&#32;', '  x  ', id="padded"),
    pytest.param(' x', '&#32;x', ' x', id="lead"),
    pytest.param('x ', 'x&#32;', 'x ', id="trail"),
    pytest.param(' ', '&#32;', ' ', id="space-only"),
    pytest.param('a  b', 'a  b', 'a  b', id="run"),
    pytest.param('\tx\t', '&#9;x&#9;', '\tx\t', id="edge-tab"),
    pytest.param('x  \n  y', 'x  <br>  y', 'x  \n  y', id="break-spaces"),
    pytest.param('<br>\r\n', '\\<br\\><br>', '<br>\n', id="br-literal"),
    pytest.param('&#32;', '\\&\\#32\\;', '&#32;', id="entity-sp"),
    pytest.param('', '', '', id="empty"),
    pytest.param(None, '', '', id="none"),
    pytest.param('http://a.b/x_y', 'http\\:\\/\\/a\\.b\\/x\\_y', 'http://a.b/x_y', id="url"),
    pytest.param('~~x~~', '\\~\\~x\\~\\~', '~~x~~', id="tilde"),
    pytest.param('[a](b)', '\\[a\\]\\(b\\)', '[a](b)', id="link"),
]


@pytest.mark.parametrize("value,source,rendered", CELL_CASES)
def test_markdown_cell(value, source, rendered):
    assert escape(value) == source
    assert _blocks(table(("C",), [(value,)])) == [("table", [["C"], [rendered]])]


def test_markdown_escapes_all_ascii_punctuation():
    assert escape(string.punctuation) == "".join("\\" + c for c in string.punctuation)
    assert _blocks(table(("C",), [(string.punctuation,)])) == [
        ("table", [["C"], [string.punctuation]])
    ]


def test_markdown_table_shape():
    rows = [("a", None, 1), ("", "b|c", 2.5)]
    assert _blocks(table(("H1", "H 2", "H|3"), rows)) == [
        ("table", [["H1", "H 2", "H|3"], ["a", "", "1"], ["", "b|c", "2.5"]])
    ]
    empty = table(("A", "B"), [])
    assert len(empty.splitlines()) == 2
    assert _blocks(empty) == [("table", [["A", "B"]])]


def test_markdown_title_keeps_edge_whitespace_and_punctuation():
    blocks = _blocks(render_markdown(Project(name="  P|1 #  ", product_version="V")))
    assert blocks[0] == ("h1", "  P|1 #  ")


def test_markdown_export_fallbacks():
    assert render_markdown(Project(name="", product_version="")) == (
        "# \\(unnamed project\\)\n"
        "\n"
        "- Product\\: unknown\n"
        "- POUs\\: none\n"
        "- Global variable lists\\: none\n"
        "\n"
        "## I\\/O table \\(0\\)\n"
        "\n"
        "| Address | Direction | Name | Type | Scope | Comment |\n"
        "|---------|-----------|------|------|-------|---------|\n"
        "\n"
        "## Variables \\(0\\)\n"
        "\n"
        "| Scope | Section | Name | Type | Address | Initial | Comment |\n"
        "|-------|---------|------|------|---------|---------|---------|\n"
    )


@pytest.mark.parametrize("sample", SAMPLE_FILES, ids=lambda path: path.stem)
def test_markdown_export_matches_fixture(sample):
    expected = (FIXTURES / f"{sample.stem}.md").read_bytes()
    assert render_markdown(parse_file(sample)).encode("utf-8") == expected


@pytest.mark.parametrize("sample", SAMPLE_FILES, ids=lambda path: path.stem)
def test_markdown_export_structure(sample):
    project = parse_file(sample)
    io_rows = io_table(project)
    variables = list(project.all_variables())
    pous = ", ".join(p.name for p in project.pous) or "none"
    gvls = ", ".join(g.name for g in project.gvls) or "none"
    io_expected = [["Address", "Direction", "Name", "Type", "Scope", "Comment"]] + [
        [_text(v) for v in (r.address, r.direction, r.name, r.type, r.scope, r.comment)]
        for r in io_rows
    ]
    var_expected = [["Scope", "Section", "Name", "Type", "Address", "Initial", "Comment"]] + [
        [_text(x) for x in (v.scope, v.section, v.name, v.type, v.address, v.initial_value,
                            v.comment)]
        for v in variables
    ]
    assert _blocks(render_markdown(project)) == [
        ("h1", project.name or "(unnamed project)"),
        ("li", f"Product: {project.product_version or 'unknown'}"),
        ("li", f"POUs: {pous}"),
        ("li", f"Global variable lists: {gvls}"),
        ("h2", f"I/O table ({len(io_rows)})"),
        ("table", io_expected),
        ("h2", f"Variables ({len(variables)})"),
        ("table", var_expected),
    ]
