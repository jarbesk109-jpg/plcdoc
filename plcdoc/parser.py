"""PLCopen XML (CODESYS export) -> :class:`plcdoc.model.Project`.

This is the only module that touches XML. Parsing goes through ``defusedxml``
because the web backend will feed it files uploaded by strangers.

Where things live in a CODESYS export (see ``docs/xml-structure.md``):

1. ``types/pous/pou``: the standard PLCopen location (empty in CODESYS exports
   that include the Device).
2. ``.../resource/addData/data[@name=".../plcopenxml/pou"]/pou``: where CODESYS
   actually puts POUs when the Device is exported.
3. ``configuration/globalVars`` and ``configuration/resource/globalVars``:
   global variable lists, directly under the resource, not inside ``addData``.

Discovery is separated from parsing: every ``pou`` element goes through
:func:`_parse_pou` and every ``*Vars`` section through :func:`_parse_variables`,
no matter where it was found.
"""

from __future__ import annotations

import os
import re
from typing import Iterator
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as DefusedET
from defusedxml.ElementTree import ParseError as _XmlSyntaxError

from plcdoc.model import GlobalVarList, Pou, Project, Task, Variable

PLCOPEN_NS_PREFIX = "http://www.plcopen.org/xml/tc6"
XHTML_NS = "http://www.w3.org/1999/xhtml"
CODESYS_POU_DATA = "http://www.3s-software.com/plcopenxml/pou"

# Section names we know how to interpret. Anything else that still ends in
# "Vars" is mapped generically and reported as a warning.
KNOWN_SECTIONS = frozenset(
    {"local", "input", "output", "inout", "temp", "external", "global", "access"}
)

# Body languages whose content is plain text (kept in Pou.body_text).
TEXT_LANGUAGES = frozenset({"ST", "IL"})

# Children of <interface> that are not variable sections.
_INTERFACE_NON_SECTIONS = frozenset({"returnType", "documentation", "addData"})

_VARS_SUFFIX = re.compile(r"^(.+)Vars$")


class ParseError(ValueError):
    """Raised when the input is not a readable PLCopen XML project."""


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


def parse_file(path: str | os.PathLike[str]) -> Project:
    """Parse a PLCopen XML file from disk."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ParseError(f"cannot read {os.fspath(path)}: {exc.strerror}") from exc
    return parse_bytes(data)


def parse_bytes(data: bytes) -> Project:
    """Parse PLCopen XML from raw bytes (a UTF-8 BOM is handled by the XML parser)."""
    try:
        root = DefusedET.fromstring(data)
    except DefusedXmlException as exc:
        raise ParseError(f"refused unsafe XML: {type(exc).__name__}") from exc
    except _XmlSyntaxError as exc:
        raise ParseError(f"malformed XML: {exc}") from exc
    return parse_element(root)


def parse_string(text: str) -> Project:
    """Parse PLCopen XML from a text string."""
    return parse_bytes(text.encode("utf-8"))


def parse_element(root: Element) -> Project:
    """Build a :class:`Project` from an already parsed ``<project>`` element."""
    ns = _plcopen_namespace(root)
    project = Project(
        name=_attr(root.find(_q(ns, "contentHeader")), "name", ""),
        product_version=_attr(root.find(_q(ns, "fileHeader")), "productVersion", ""),
    )
    _collect_pous(root, ns, project)
    _collect_gvls(root, ns, project)
    _collect_tasks(root, ns, project)
    return project


# --------------------------------------------------------------------------- #
# Discovery: the three locations
# --------------------------------------------------------------------------- #


def _collect_pous(root: Element, ns: str, project: Project) -> None:
    seen: dict[str, str] = {}
    for elem, location in _iter_pou_elements(root, ns):
        pou = _parse_pou(elem, ns, project.warnings)
        if pou.name in seen:
            project.warnings.append(
                f"duplicate POU {pou.name!r} in {location} ignored "
                f"(already read from {seen[pou.name]})"
            )
            continue
        seen[pou.name] = location
        project.pous.append(pou)


def _iter_pou_elements(root: Element, ns: str) -> Iterator[tuple[Element, str]]:
    # Location 1: standard PLCopen.
    standard_path = "/".join(["." , _q(ns, "types"), _q(ns, "pous"), _q(ns, "pou")])
    for elem in root.findall(standard_path):
        yield elem, "types/pous"
    # Location 2: CODESYS vendor extension. The <data> element sits in the
    # addData of a resource in the samples; look at every <data> element with
    # the CODESYS pou name so a configuration-level placement is found as well.
    for data in root.iter(_q(ns, "data")):
        if data.get("name") != CODESYS_POU_DATA:
            continue
        for elem in data.findall(_q(ns, "pou")):
            yield elem, "addData/data[pou]"


def _collect_gvls(root: Element, ns: str, project: Project) -> None:
    # Location 3: only configuration- and resource-level globalVars are GVLs.
    # A globalVars section inside a POU interface belongs to that POU instead.
    for configuration in root.iter(_q(ns, "configuration")):
        holders = [configuration, *configuration.findall(_q(ns, "resource"))]
        for holder in holders:
            for elem in holder.findall(_q(ns, "globalVars")):
                name = elem.get("name", "")
                gvl = GlobalVarList(name=name)
                gvl.variables = _parse_variables(elem, ns, "global", name, project.warnings)
                project.gvls.append(gvl)


def _collect_tasks(root: Element, ns: str, project: Project) -> None:
    for elem in root.iter(_q(ns, "task")):
        priority_text = elem.get("priority")
        task = Task(
            name=elem.get("name", ""),
            interval=elem.get("interval"),
            priority=int(priority_text) if priority_text and priority_text.isdigit() else None,
            programs=[
                inst.get("name", "") for inst in elem.findall(_q(ns, "pouInstance"))
            ],
        )
        project.tasks.append(task)


# --------------------------------------------------------------------------- #
# Parsing: POU, variables, body
# --------------------------------------------------------------------------- #


def _parse_pou(elem: Element, ns: str, warnings: list[str]) -> Pou:
    name = elem.get("name", "")
    pou = Pou(name=name, pou_type=elem.get("pouType", ""))

    interface = elem.find(_q(ns, "interface"))
    if interface is not None:
        for child in interface:
            local = _local(child.tag)
            if local == "returnType":
                pou.return_type = _type_name(child, ns, f"{name} return type", warnings)
            elif local in _INTERFACE_NON_SECTIONS:
                continue
            else:
                section = _section_name(local)
                if section is None:
                    warnings.append(f"{name}: unknown interface element <{local}> skipped")
                    continue
                if section not in KNOWN_SECTIONS:
                    warnings.append(f"{name}: unrecognised variable section <{local}>")
                pou.variables.extend(_parse_variables(child, ns, section, name, warnings))

    body = elem.find(_q(ns, "body"))
    if body is not None:
        _parse_body(body, ns, pou)
    return pou


def _section_name(local_tag: str) -> str | None:
    """``localVars`` -> ``local``, ``inOutVars`` -> ``inout``; None if not a *Vars tag."""
    match = _VARS_SUFFIX.match(local_tag)
    return match.group(1).lower() if match else None


def _parse_variables(
    section_elem: Element, ns: str, section: str, scope: str, warnings: list[str]
) -> list[Variable]:
    variables = []
    for elem in section_elem.findall(_q(ns, "variable")):
        name = elem.get("name", "")
        where = f"{scope}.{name}"
        type_elem = elem.find(_q(ns, "type"))
        type_name = _type_name(type_elem, ns, where, warnings) if type_elem is not None else ""
        is_derived = type_elem is not None and type_elem.find(_q(ns, "derived")) is not None
        variables.append(
            Variable(
                name=name,
                type=type_name,
                scope=scope,
                section=section,
                is_derived=is_derived,
                address=elem.get("address"),
                initial_value=_initial_value(elem, ns, where, warnings),
                comment=_documentation(elem, ns),
            )
        )
    return variables


def _type_name(container: Element | None, ns: str, where: str, warnings: list[str]) -> str:
    """Type text from a ``<type>`` or ``<returnType>`` element.

    ``<BOOL />`` -> ``BOOL``; ``<derived name="CTU" />`` -> ``CTU``. Anything
    more complex (arrays, sized strings, ...) has not been seen in a sample yet,
    so it is rendered best-effort from the tag and attributes and reported.
    """
    if container is None:
        return ""
    children = list(container)
    if not children:
        return ""
    child = children[0]
    local = _local(child.tag)
    if local == "derived":
        return child.get("name", "")
    if not child.attrib and len(child) == 0:
        return local
    attrs = ",".join(f"{k}={v}" for k, v in sorted(child.attrib.items()))
    rendered = f"{local.upper()}({attrs})" if attrs else local.upper()
    warnings.append(f"{where}: type <{local}> rendered best-effort as {rendered}")
    return rendered


def _initial_value(
    var_elem: Element, ns: str, where: str, warnings: list[str]
) -> str | None:
    init = var_elem.find(_q(ns, "initialValue"))
    if init is None:
        return None
    simple = init.find(_q(ns, "simpleValue"))
    if simple is not None:
        return simple.get("value")
    kinds = ", ".join(_local(c.tag) for c in init) or "empty"
    warnings.append(f"{where}: initial value of kind {kinds} not supported, ignored")
    return None


def _documentation(elem: Element, ns: str) -> str:
    doc = elem.find(_q(ns, "documentation"))
    if doc is None:
        return ""
    xhtml = doc.find(_q(XHTML_NS, "xhtml"))
    source = xhtml if xhtml is not None else doc
    return "".join(source.itertext()).strip()


def _parse_body(body: Element, ns: str, pou: Pou) -> None:
    for child in body:
        local = _local(child.tag)
        if local in ("addData", "documentation"):
            continue
        pou.body_language = local
        if local in TEXT_LANGUAGES:
            xhtml = child.find(_q(XHTML_NS, "xhtml"))
            source = xhtml if xhtml is not None else child
            text = "".join(source.itertext())
            pou.body_text = text.replace("\r\n", "\n").replace("\r", "\n")
        return


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _plcopen_namespace(root: Element) -> str:
    """Return the tc6 namespace of the root, accepting any tc6 schema version."""
    ns, local = _split(root.tag)
    if local != "project" or not ns.startswith(PLCOPEN_NS_PREFIX):
        raise ParseError(
            f"not a PLCopen XML project: root element is <{local}> "
            f"in namespace {ns or '(none)'}"
        )
    return ns


def _split(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return "", tag


def _local(tag: str) -> str:
    return _split(tag)[1]


def _q(ns: str, local: str) -> str:
    return "{" + ns + "}" + local


def _attr(elem: Element | None, name: str, default: str) -> str:
    return elem.get(name, default) if elem is not None else default
