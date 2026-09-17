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

Readable fields (``Variable.type``, ``Variable.initial_value``,
``Pou.return_type``) never contain XML. Shapes that have no short readable
form get a placeholder and the full detail lives in the ``*_xml`` fields.
"""

from __future__ import annotations

import os
import re
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
CODESYS_TASK_SETTINGS = "http://www.3s-software.com/plcopenxml/tasksettings"
CODESYS_OBJECT_ID = "http://www.3s-software.com/plcopenxml/objectid"
CODESYS_FBD_ELEMENT_TYPE = "http://www.3s-software.com/plcopenxml/fbdelementtype"
QUALIFIERS = ("retain", "nonretain", "persistent", "constant")

# Placeholders for readable fields whose detail lives in the matching *_xml field.
ARRAY_PLACEHOLDER = "(array)"
STRUCT_PLACEHOLDER = "(struct)"
UNKNOWN_PLACEHOLDER = "(unknown)"

# IEC 61131-3 elementary type names. Only used to decide whether a leaf type
# tag deserves a warning; every leaf tag is rendered by its own name.
IEC_ELEMENTARY_TYPES = frozenset(
    "BOOL BYTE WORD DWORD LWORD SINT INT DINT LINT USINT UINT UDINT ULINT "
    "REAL LREAL TIME LTIME DATE LDATE DT LDT TOD LTOD CHAR WCHAR STRING WSTRING "
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
                settings=_task_settings(elem, ns),
            )
            project.tasks.append(task)


def _task_settings(task: Element, ns: str) -> dict[str, str]:
    """CODESYS ``TaskSettings`` flattened to ``{"KindOfTask": "Cyclic", "Watchdog.Enabled": "false"}``."""
    settings: dict[str, str] = {}
    for data in _data_elements(task, ns, CODESYS_TASK_SETTINGS):
        for node in data:
            if not isinstance(node.tag, str):
                continue
            settings.update(node.attrib)
            for child in node:
                if isinstance(child.tag, str):
                    prefix = _local(child.tag)
                    settings.update({f"{prefix}.{key}": value for key, value in child.attrib.items()})
    return settings


def _data_elements(elem: Element, ns: str, name: str) -> Iterator[Element]:
    """Direct ``addData/data[@name=name]`` children of *elem*."""
    for data in elem.findall("/".join([_q(ns, "addData"), _q(ns, "data")])):
        if data.get("name") == name:
            yield data


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
        comment=_documentation(elem, ns),
    )

    interface = elem.find(_q(ns, "interface"))
    if interface is not None:
        if not pou.comment:
            pou.comment = _documentation(interface, ns)
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
    for data in _data_elements(section, ns, CODESYS_MIXED_ATTRS):
        for mixed in data.findall(_q(ns, "MixedAttrsVarList")):
            for block in mixed.findall(_q(ns, "globalVars")):
                if block.get("name") != section.get("name"):
                    continue
                for var in block.findall(_q(ns, "variable")):
                    result[var.get("name", "")] = _qualifiers(block)
    return result


def _type_name(container: Element | None, ns: str, where: str, warnings: list[str]) -> str:
    """Readable type from a ``<type>``, ``<returnType>`` or ``<baseType>`` element.

    ``BOOL``, ``CTU``, ``STRING(20)``, ``ARRAY[1..4] OF REAL``. Shapes without a
    short readable form become ``(struct)`` or ``(unknown)``; the canonical XML
    in the matching ``*_xml`` field keeps the detail.
    """
    if container is None:
        return ""
    children = [child for child in container if isinstance(child.tag, str)]
    if len(children) != 1:
        warnings.append(
            f"{where}: type element with {len(children)} children recorded as {UNKNOWN_PLACEHOLDER}"
        )
        return UNKNOWN_PLACEHOLDER
    return _render_type(children[0], ns, where, warnings)


def _render_type(child: Element, ns: str, where: str, warnings: list[str]) -> str:
    namespace, local = _split(child.tag)
    if namespace != ns:
        warnings.append(f"{where}: vendor type <{local}> recorded as {UNKNOWN_PLACEHOLDER}")
        return UNKNOWN_PLACEHOLDER
    if local == "derived":
        name = child.get("name")
        if name:
            return name
        warnings.append(f"{where}: derived type without a name recorded as {UNKNOWN_PLACEHOLDER}")
        return UNKNOWN_PLACEHOLDER
    if local in ("string", "wstring"):
        length = child.get("length")
        return local.upper() + (f"({length})" if length is not None else "")
    if local == "array":
        dimensions = child.findall(_q(ns, "dimension"))
        base = child.find(_q(ns, "baseType"))
        if dimensions and base is not None:
            bounds = ", ".join(f"{d.get('lower', '?')}..{d.get('upper', '?')}" for d in dimensions)
            return f"ARRAY[{bounds}] OF {_type_name(base, ns, where, warnings)}"
        warnings.append(f"{where}: array without dimension/baseType recorded as {ARRAY_PLACEHOLDER}")
        return ARRAY_PLACEHOLDER
    if local == "struct":
        return STRUCT_PLACEHOLDER
    if len(child) == 0:
        if local not in IEC_ELEMENTARY_TYPES:
            warnings.append(f"{where}: non-IEC type <{local}> recorded by tag name")
        return local
    warnings.append(f"{where}: type <{local}> recorded as {UNKNOWN_PLACEHOLDER}")
    return UNKNOWN_PLACEHOLDER


def _initial_value(
    var_elem: Element, ns: str, where: str, warnings: list[str]
) -> str | None:
    init = var_elem.find(_q(ns, "initialValue"))
    if init is None:
        return None
    children = [child for child in init if isinstance(child.tag, str)]
    if len(children) == 1:
        value = children[0]
        if value.tag == _q(ns, "simpleValue") and "value" in value.attrib:
            return value.attrib["value"]
        if value.tag == _q(ns, "arrayValue"):
            return ARRAY_PLACEHOLDER
        if value.tag == _q(ns, "structValue"):
            return STRUCT_PLACEHOLDER
    warnings.append(f"{where}: initial value recorded as {UNKNOWN_PLACEHOLDER}, see initial_value_xml")
    return UNKNOWN_PLACEHOLDER


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
    """Documented layout/GUID/network-title noise inside graphical bodies."""
    if not isinstance(elem.tag, str):  # XML comments passed via parse_element
        return True
    namespace, local = _split(elem.tag)
    if not namespace.startswith(PLCOPEN_NS_PREFIX):
        return False  # A vendor's similarly named element may carry real semantics.
    if local in ("position", "relPosition", "comment"):
        return True
    if local == "data" and elem.get("name") == CODESYS_OBJECT_ID:
        return True
    if local == "vendorElement":
        for data in _data_elements(elem, namespace, CODESYS_FBD_ELEMENT_TYPE):
            return any(
                isinstance(child.tag, str) and _local(child.tag) == "ElementType"
                and (child.text or "").strip() == "networktitle" for child in data
            )
    return False


_XML_NS = "http://www.w3.org/XML/1998/namespace"


def _canonical_xml(elem: Element, *, graphical: bool = False) -> str:
    """Canonical XML with deterministic prefixes and lossless text content.

    Sorted namespace URIs receive ``n0``, ``n1``, ... independently of source
    prefixes, attribute order and ``ET.register_namespace``. C14N 2.0 sorts
    attributes. Only indentation in element-only content is removed, respecting
    inherited ``xml:space``; leaf and mixed-content text stays verbatim.
    Graphical bodies also lose the documented noise elements. The caller's
    tree is never modified and no Element escapes into the model.

    Assigning prefixes ourselves avoids CPython's prefix rewriter emitting
    invalid empty-namespace declarations next to unprefixed attributes.
    """
    fragment = _rebuild(elem, graphical)
    namespaces = {
        _split(name)[0]
        for node in fragment.iter()
        for name in (node.tag, *node.attrib)
    } - {"", _XML_NS}
    prefixes = {namespace: f"n{i}" for i, namespace in enumerate(sorted(namespaces))}
    for node in fragment.iter():
        node.tag = _prefixed(node.tag, prefixes)
        node.attrib = {_prefixed(key, prefixes): value for key, value in node.attrib.items()}
    for namespace, prefix in prefixes.items():
        fragment.set(f"xmlns:{prefix}", namespace)
    # tostring emits literal CR in text. Keep parsed character references such
    # as &#13; from being normalized to LF when C14N parses the serialization.
    serialized = ET.tostring(fragment, encoding="unicode").replace("\r", "&#13;")
    return ET.canonicalize(serialized)


def _prefixed(tag: str, prefixes: dict[str, str]) -> str:
    """``{ns}local`` -> ``n0:local`` using the fragment's fixed prefix map."""
    namespace, local = _split(tag)
    if not namespace:
        return local
    if namespace == _XML_NS:
        return f"xml:{local}"
    return f"{prefixes[namespace]}:{local}"


def _rebuild(elem: Element, graphical: bool, preserve_space: bool = False) -> Element:
    # A filtered rebuild instead of deepcopy: it drops the root's tail (which
    # tostring would emit after the element), XML comments and, for graphical
    # bodies, the noise elements. canonicalize's exclude_tags cannot filter by
    # attribute, which the objectid/network-title noise needs.
    space = elem.get(_q(_XML_NS, "space"))
    if space in ("preserve", "default"):
        preserve_space = space == "preserve"
    element_only = any(isinstance(child.tag, str) for child in elem) and not any(
        text and text.strip(" \t\r\n") for text in (elem.text, *(child.tail for child in elem))
    )
    drop_indentation = element_only and not preserve_space
    copy = Element(elem.tag, dict(elem.attrib))
    copy.text = None if drop_indentation else elem.text
    for child in elem:
        if isinstance(child.tag, str) and not (graphical and _graphical_noise(child)):
            copy.append(_rebuild(child, graphical, preserve_space))
        # Tails belong to this parent's content, even when their element was
        # excluded. A child's xml:space setting never governs its own tail.
        if not drop_indentation and child.tail:
            if len(copy):
                copy[-1].tail = (copy[-1].tail or "") + child.tail
            else:
                copy.text = (copy.text or "") + child.tail
    return copy


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
