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
from copy import deepcopy
from typing import Iterator
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as DefusedET
from defusedxml.ElementTree import ParseError as _XmlSyntaxError

from plcdoc.model import (
    GlobalVarList, GraphicalElement, Pou, PouInstance, Project, Task, Variable,
)

PLCOPEN_NS_PREFIX = "http://www.plcopen.org/xml/tc6"
XHTML_NS = "http://www.w3.org/1999/xhtml"
CODESYS_POU_DATA = "http://www.3s-software.com/plcopenxml/pou"
CODESYS_MIXED_ATTRS = "http://www.3s-software.com/plcopenxml/mixedattrsvarlist"
QUALIFIERS = ("retain", "nonretain", "persistent", "constant")
ELEMENTARY_TYPES = frozenset(
    "BOOL BYTE WORD DWORD LWORD SINT INT DINT LINT USINT UINT UDINT ULINT "
    "REAL LREAL TIME LTIME DATE LDATE DT LDT TOD LTOD CHAR WCHAR "
    "ANY ANY_DERIVED ANY_ELEMENTARY ANY_MAGNITUDE ANY_NUM ANY_REAL "
    "ANY_INT ANY_BIT ANY_STRING ANY_DATE".split()
)

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
    seen: dict[tuple[str | None, str | None, str], list[Pou]] = {}
    for elem, configuration, application in _iter_pou_elements(root, ns):
        pou = _parse_pou(elem, ns, project.warnings, configuration, application)
        key = (configuration, application, pou.name)
        previous = seen.setdefault(key, [])
        if previous:
            identical = pou in previous
            action = "identical definition ignored" if identical else "conflicting definition retained"
            project.warnings.append(
                f"duplicate POU {pou.name!r} in {configuration!r}/{application!r}: {action}"
            )
            if identical:
                continue
        previous.append(pou)
        project.pous.append(pou)


def _iter_owned_elements(
    elem: Element, ns: str, configuration: str | None = None, application: str | None = None,
) -> Iterator[tuple[Element, str | None, str | None]]:
    """Keep the enclosing device/application while walking vendor extensions."""
    if elem.tag == _q(ns, "configuration"):
        configuration, application = elem.get("name", ""), None
    elif elem.tag == _q(ns, "resource"):
        application = elem.get("name", "")
    yield elem, configuration, application
    for child in elem:
        yield from _iter_owned_elements(child, ns, configuration, application)


def _iter_pou_elements(
    root: Element, ns: str,
) -> Iterator[tuple[Element, str | None, str | None]]:
    # Location 1: standard PLCopen.
    standard_path = "/".join([".", _q(ns, "types"), _q(ns, "pous"), _q(ns, "pou")])
    for elem in root.findall(standard_path):
        yield elem, None, None
    # Location 2: CODESYS vendor extension. The <data> element sits in the
    # addData of a resource in the samples; look at every <data> element with
    # the CODESYS pou name so a configuration-level placement is found as well.
    for data, configuration, application in _iter_owned_elements(root, ns):
        if data.tag != _q(ns, "data") or data.get("name") != CODESYS_POU_DATA:
            continue
        for elem in data.findall(_q(ns, "pou")):
            yield elem, configuration, application


def _iter_holders(
    root: Element, ns: str,
) -> Iterator[tuple[Element, str, str | None]]:
    path = "/".join(_q(ns, tag) for tag in ("instances", "configurations", "configuration"))
    for configuration in root.findall(path):
        name = configuration.get("name", "")
        yield configuration, name, None
        for resource in configuration.findall(_q(ns, "resource")):
            yield resource, name, resource.get("name", "")


def _collect_gvls(root: Element, ns: str, project: Project) -> None:
    # Location 3: only configuration- and resource-level globalVars are GVLs.
    # A globalVars section inside a POU interface belongs to that POU instead.
    for holder, configuration, application in _iter_holders(root, ns):
        for elem in holder.findall(_q(ns, "globalVars")):
            name = elem.get("name", "")
            gvl = GlobalVarList(name=name, configuration=configuration, application=application)
            gvl.variables = _parse_variables(
                elem, ns, "global", name, project.warnings, configuration, application,
            )
            project.gvls.append(gvl)


def _collect_tasks(root: Element, ns: str, project: Project) -> None:
    for holder, configuration, application in _iter_holders(root, ns):
        for elem in holder.findall(_q(ns, "task")):
            priority_text = elem.get("priority")
            task = Task(
                name=elem.get("name", ""),
                configuration=configuration,
                application=application,
                interval=elem.get("interval"),
                priority=int(priority_text) if priority_text and priority_text.isdigit() else None,
                programs=[
                    PouInstance(
                        instance_name=inst.get("name", ""),
                        type_name=inst.get("typeName") or inst.get("name", ""),
                    )
                    for inst in elem.findall(_q(ns, "pouInstance"))
                ],
            )
            project.tasks.append(task)


# --------------------------------------------------------------------------- #
# Parsing: POU, variables, body
# --------------------------------------------------------------------------- #


def _parse_pou(
    elem: Element, ns: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> Pou:
    name = elem.get("name", "")
    pou = Pou(
        name=name, pou_type=elem.get("pouType", ""),
        configuration=configuration, application=application,
    )

    interface = elem.find(_q(ns, "interface"))
    if interface is not None:
        for child in interface:
            local = _local(child.tag)
            if local == "returnType":
                pou.return_type = _type_name(child, ns, f"{name} return type", warnings)
                pou.return_type_xml = _canonical_xml(child)
            elif local in _INTERFACE_NON_SECTIONS:
                continue
            else:
                section = _section_name(local)
                if section is None:
                    warnings.append(f"{name}: unknown interface element <{local}> skipped")
                    continue
                if section not in KNOWN_SECTIONS:
                    warnings.append(f"{name}: unrecognised variable section <{local}>")
                pou.variables.extend(_parse_variables(
                    child, ns, section, name, warnings, configuration, application,
                ))

    body = elem.find(_q(ns, "body"))
    if body is not None:
        _parse_body(body, ns, pou)
    return pou


def _section_name(local_tag: str) -> str | None:
    """``localVars`` -> ``local``, ``inOutVars`` -> ``inout``; None if not a *Vars tag."""
    match = _VARS_SUFFIX.match(local_tag)
    return match.group(1).lower() if match else None


def _parse_variables(
    section_elem: Element, ns: str, section: str, scope: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> list[Variable]:
    variables = []
    qualifiers = _variable_qualifiers(section_elem, ns)
    default_qualifiers = _qualifiers(section_elem)
    for elem in section_elem.findall(_q(ns, "variable")):
        name = elem.get("name", "")
        where = f"{scope}.{name}"
        type_elem = elem.find(_q(ns, "type"))
        type_name = _type_name(type_elem, ns, where, warnings) if type_elem is not None else ""
        derived_types = list(dict.fromkeys(
            child.get("name", "") for child in type_elem.iter(_q(ns, "derived"))
        )) if type_elem is not None else []
        init = elem.find(_q(ns, "initialValue"))
        variables.append(
            Variable(
                name=name,
                type=type_name,
                scope=scope,
                section=section,
                configuration=configuration,
                application=application,
                is_derived=bool(derived_types),
                derived_types=derived_types,
                type_xml=_canonical_xml(type_elem) if type_elem is not None else None,
                initial_value_xml=_canonical_xml(init) if init is not None else None,
                address=elem.get("address"),
                initial_value=_initial_value(elem, ns, where, warnings),
                comment=_documentation(elem, ns),
                **qualifiers.get(name, default_qualifiers),
            )
        )
    return variables


def _qualifiers(elem: Element) -> dict[str, bool]:
    return {name: elem.get(name, "false") in ("true", "1") for name in QUALIFIERS}


def _variable_qualifiers(section: Element, ns: str) -> dict[str, dict[str, bool]]:
    """MixedAttrsVarList contains qualifier overlays, never new declarations."""
    result = {}
    for data in section.findall(f"{_q(ns, 'addData')}/{_q(ns, 'data')}"):
        if data.get("name") != CODESYS_MIXED_ATTRS:
            continue
        for mixed in data.findall(_q(ns, "MixedAttrsVarList")):
            for block in mixed.findall(_q(ns, "globalVars")):
                if block.get("name") != section.get("name"):
                    continue
                for var in block.findall(_q(ns, "variable")):
                    result[var.get("name", "")] = _qualifiers(block)
    return result


def _type_name(container: Element | None, ns: str, where: str, warnings: list[str]) -> str:
    """Readable elementary/derived/array/string types; canonical XML otherwise."""
    if container is None:
        return ""
    if len(container) != 1:
        warnings.append(f"{where}: nonstandard type preserved as canonical XML")
        return _canonical_xml(container)
    return _render_type(container[0], ns, where, warnings)


def _render_type(child: Element, ns: str, where: str, warnings: list[str]) -> str:
    local = _local(child.tag)
    if child.tag == _q(ns, local):
        if local in ELEMENTARY_TYPES and not child.attrib and len(child) == 0:
            return local
        if local == "derived" and set(child.attrib) == {"name"} and len(child) == 0:
            return child.attrib["name"]
        if (
            local in ("string", "wstring")
            and not (child.attrib.keys() - {"length"}) and len(child) == 0
        ):
            length = child.get("length")
            return local.upper() + (f"({length})" if length is not None else "")
        if local == "array" and not child.attrib:
            dimensions = child.findall(_q(ns, "dimension"))
            bases = child.findall(_q(ns, "baseType"))
            if (
                dimensions and len(bases) == 1 and len(child) == len(dimensions) + 1
                and all(set(d.attrib) == {"lower", "upper"} and len(d) == 0 for d in dimensions)
            ):
                bounds = ", ".join(f"{d.attrib['lower']}..{d.attrib['upper']}" for d in dimensions)
                base = _type_name(bases[0], ns, where, warnings)
                return f"ARRAY[{bounds}] OF {base}"
    warnings.append(f"{where}: type <{local}> preserved as canonical XML")
    return _canonical_xml(child)


def _initial_value(
    var_elem: Element, ns: str, where: str, warnings: list[str]
) -> str | None:
    init = var_elem.find(_q(ns, "initialValue"))
    if init is None:
        return None
    if len(init) == 1:
        value = init[0]
        if (
            value.tag == _q(ns, "simpleValue")
            and set(value.attrib) == {"value"} and len(value) == 0
        ):
            return value.attrib["value"]
        if value.tag in (_q(ns, "arrayValue"), _q(ns, "structValue")):
            return _canonical_xml(init)
    warnings.append(f"{where}: nonstandard initial value preserved as canonical XML")
    return _canonical_xml(init)


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
        else:
            pou.body_xml = _canonical_xml(child, graphical=True)
            for instruction in child:
                if _graphical_noise(instruction):
                    continue
                variable = instruction.find(_q(ns, "variable"))
                pou.graphical_body.append(GraphicalElement(
                    kind=_local(instruction.tag),
                    local_id=instruction.get("localId"),
                    variable="".join(variable.itertext()).strip() if variable is not None else None,
                    negated=(instruction.get("negated") in ("true", "1"))
                    if "negated" in instruction.attrib else None,
                    storage=instruction.get("storage"),
                    edge=instruction.get("edge"),
                    incoming_ref_local_ids=[
                        connection.attrib["refLocalId"]
                        for point in instruction.iter(_q(ns, "connectionPointIn"))
                        for connection in point.findall(_q(ns, "connection"))
                        if "refLocalId" in connection.attrib
                    ],
                    xml=_canonical_xml(instruction, graphical=True),
                ))
        return


def _graphical_noise(elem: Element) -> bool:
    if not isinstance(elem.tag, str):  # XML comments passed via parse_element
        return True
    namespace, local = _split(elem.tag)
    if not namespace.startswith(PLCOPEN_NS_PREFIX):
        return False  # A vendor's similarly named element may carry real semantics.
    if local in ("position", "relPosition", "comment"):
        return True
    if local == "data" and elem.get("name") == "http://www.3s-software.com/plcopenxml/objectid":
        return True
    if local == "vendorElement":
        for data in elem.findall(f"{_q(namespace, 'addData')}/{_q(namespace, 'data')}"):
            if data.get("name") == "http://www.3s-software.com/plcopenxml/fbdelementtype":
                return any(
                    isinstance(child.tag, str) and _local(child.tag) == "ElementType"
                    and (child.text or "").strip() == "networktitle" for child in data
                )
    return False


def _canonical_xml(elem: Element, *, graphical: bool = False) -> str:
    """Namespace/attribute-order independent XML, without indentation or tail.

    Preserve leaf text and significant mixed-content whitespace. Only graphical
    serialization removes the explicitly documented layout/network/GUID noise.
    No Element objects escape into the model, and the caller's tree is untouched.
    """
    clone = deepcopy(elem)

    def clean(node: Element, preserve_space: bool = False) -> None:
        space = node.get("{http://www.w3.org/XML/1998/namespace}space")
        if space is not None:
            preserve_space = space == "preserve"
        # Strip formatting only in element-only content, never in mixed text or
        # in an xml:space="preserve" subtree. Tails belong to the parent.
        element_only = len(node) > 0 and not preserve_space and not any(
            text and text.strip() for text in [node.text, *(child.tail for child in node)]
        )
        for child in list(node):
            if not isinstance(child.tag, str) or (graphical and _graphical_noise(child)):
                node.remove(child)
            else:
                clean(child, preserve_space)
        if element_only:
            node.text = None
            for child in node:
                child.tail = None
        attributes = sorted(node.attrib.items())
        node.attrib.clear()
        node.attrib.update(attributes)

    clean(clone)
    clone.tail = None
    return ET.canonicalize(ET.tostring(clone, encoding="unicode"))


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
