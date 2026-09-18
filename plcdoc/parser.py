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
    Accessor, Action, Attribute, DataType, EnumValue, GlobalVarList, GraphicalElement,
    Method, Pou, PouInstance, Project, Property, StructureNode, Task, Variable,
)

PLCOPEN_NS_PREFIX = "http://www.plcopen.org/xml/tc6"
XHTML_NS = "http://www.w3.org/1999/xhtml"
CODESYS_POU_DATA = "http://www.3s-software.com/plcopenxml/pou"
CODESYS_DATATYPE_DATA = "http://www.3s-software.com/plcopenxml/datatype"
CODESYS_ATTRIBUTES = "http://www.3s-software.com/plcopenxml/attributes"
CODESYS_METHOD_DATA = "http://www.3s-software.com/plcopenxml/method"
CODESYS_PROPERTY_DATA = "http://www.3s-software.com/plcopenxml/property"
CODESYS_PROJECT_STRUCTURE = "http://www.3s-software.com/plcopenxml/projectstructure"

# Elements whose addData/objectid identifies them in ProjectStructure -> node kind.
_OBJECT_KINDS = {
    "configuration": "configuration",
    "resource": "application",
    "globalVars": "gvl",
    "pou": "pou",
    "action": "action",
    "dataType": "datatype",
    "task": "task",
    "Libraries": "libraries",
}
# Elements that carry their ObjectId as an attribute instead.
_OBJECT_ID_ATTRIBUTE_KINDS = {"Method": "method", "Property": "property"}
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
    _collect(root, ns, project)
    project.structure = _collect_structure(root, ns, _object_kinds(root, ns))
    return project


# --------------------------------------------------------------------------- #
# Discovery: one ownership walk over the whole document
# --------------------------------------------------------------------------- #


def _collect(root: Element, ns: str, project: Project) -> None:
    """Find every POU, GVL and task together with its owner in one walk.

    Standard locations (``types/pous``, project scope) come first. Then a
    single document-order walk carries the enclosing configuration/resource
    names: CODESYS ``data[@name=".../pou"]`` elements contribute POUs, and
    ``configuration`` / ``resource`` elements contribute their *direct*
    ``globalVars`` and ``task`` children (a ``globalVars`` inside a POU
    interface belongs to that POU, never to the project).
    """
    unique_pous = _UniqueByOwner("POU", project.warnings)
    unique_types = _UniqueByOwner("data type", project.warnings)
    standard_pous = "/".join([".", _q(ns, "types"), _q(ns, "pous"), _q(ns, "pou")])
    standard_types = "/".join([".", _q(ns, "types"), _q(ns, "dataTypes"), _q(ns, "dataType")])
    for elem in root.findall(standard_pous):
        unique_pous.add(project.pous, _parse_pou(elem, ns, project.warnings, None, None))
    for elem in root.findall(standard_types):
        unique_types.add(
            project.data_types, _parse_data_type(elem, ns, project.warnings, None, None),
        )
    for elem, configuration, application in _walk(root, ns):
        if elem.tag == _q(ns, "data"):
            if elem.get("name") == CODESYS_POU_DATA:
                for pou_elem in elem.findall(_q(ns, "pou")):
                    unique_pous.add(
                        project.pous,
                        _parse_pou(pou_elem, ns, project.warnings, configuration, application),
                    )
            elif elem.get("name") == CODESYS_DATATYPE_DATA:
                for type_elem in elem.findall(_q(ns, "dataType")):
                    unique_types.add(
                        project.data_types,
                        _parse_data_type(type_elem, ns, project.warnings, configuration, application),
                    )
        elif elem.tag in (_q(ns, "configuration"), _q(ns, "resource")):
            for gvl_elem in elem.findall(_q(ns, "globalVars")):
                project.gvls.append(
                    _parse_gvl(gvl_elem, ns, project.warnings, configuration, application)
                )
            for task_elem in elem.findall(_q(ns, "task")):
                project.tasks.append(_parse_task(task_elem, ns, configuration, application))


def _walk(
    elem: Element, ns: str, configuration: str | None = None, application: str | None = None,
) -> Iterator[tuple[Element, str | None, str | None]]:
    """Every element in document order with its enclosing configuration/resource names.

    Ownership changes at ``configuration`` (resets the application) and at
    ``resource``. The same walk serves POUs, GVLs and tasks, so all of them
    agree on who owns what, wherever CODESYS nests the element.
    """
    if elem.tag == _q(ns, "configuration"):
        configuration, application = elem.get("name", ""), None
    elif elem.tag == _q(ns, "resource"):
        application = elem.get("name", "")
    yield elem, configuration, application
    for child in elem:
        yield from _walk(child, ns, configuration, application)


class _UniqueByOwner:
    """Collapse identical definitions within one owner; keep conflicting ones with a warning."""

    def __init__(self, label: str, warnings: list[str]) -> None:
        self._label = label
        self._warnings = warnings
        self._seen: dict[tuple[str | None, str | None, str], list] = {}

    def add(self, target: list, obj) -> None:
        key = (obj.configuration, obj.application, obj.name)
        previous = self._seen.setdefault(key, [])
        if previous:
            identical = obj in previous
            action = "identical definition ignored" if identical else "conflicting definition retained"
            self._warnings.append(
                f"duplicate {self._label} {obj.name!r} in "
                f"{obj.configuration!r}/{obj.application!r}: {action}"
            )
            if identical:
                return
        previous.append(obj)
        target.append(obj)


def _object_kinds(root: Element, ns: str) -> dict[str, str]:
    """ObjectId -> node kind for every exported object, used only to label ProjectStructure.

    The GUID sits in ``addData/data[@name=".../objectid"]/ObjectId`` on most
    objects and in an ``ObjectId`` attribute on CODESYS ``Method`` /
    ``Property``. Nothing here is stored in the model (Decision 010).
    """
    kinds: dict[str, str] = {}
    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue
        namespace, local = _split(elem.tag)
        if namespace != ns:
            continue
        if local in _OBJECT_KINDS:
            for data in _data_elements(elem, ns, CODESYS_OBJECT_ID):
                for object_id in data.findall(_q(ns, "ObjectId")):
                    if object_id.text and object_id.text.strip():
                        kinds.setdefault(object_id.text.strip(), _OBJECT_KINDS[local])
        elif local in _OBJECT_ID_ATTRIBUTE_KINDS and elem.get("ObjectId"):
            kinds.setdefault(elem.get("ObjectId", ""), _OBJECT_ID_ATTRIBUTE_KINDS[local])
    return kinds


def _collect_structure(root: Element, ns: str, kinds: dict[str, str]) -> list[StructureNode]:
    """Every ``ProjectStructure`` tree under the project's own addData, labelled by *kinds*."""

    def node(obj: Element) -> StructureNode:
        return StructureNode(
            name=obj.get("Name", ""),
            kind=kinds.get(obj.get("ObjectId", "")),
            children=[node(child) for child in obj.findall(_q(ns, "Object"))],
        )

    return [
        node(obj)
        for data in _data_elements(root, ns, CODESYS_PROJECT_STRUCTURE)
        for structure in data.findall(_q(ns, "ProjectStructure"))
        for obj in structure.findall(_q(ns, "Object"))
    ]


def _parse_gvl(
    elem: Element, ns: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> GlobalVarList:
    name = elem.get("name", "")
    gvl = GlobalVarList(name=name, configuration=configuration, application=application)
    gvl.variables = _parse_variables(elem, ns, "global", name, warnings, configuration, application)
    return gvl


def _parse_task(
    elem: Element, ns: str, configuration: str | None, application: str | None,
) -> Task:
    priority_text = elem.get("priority")
    return Task(
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
# Parsing: data types
# --------------------------------------------------------------------------- #

# Children of <dataType> the parser interprets; anything else is residual.
_DATA_TYPE_CHILDREN = frozenset({"baseType", "documentation", "addData"})


def _parse_data_type(
    elem: Element, ns: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> DataType:
    name = elem.get("name", "")
    data_type = DataType(
        name=name, kind="other", comment=_documentation(elem, ns),
        configuration=configuration, application=application,
        attributes=_attributes(elem, ns),
        vendor_xml=_residual_xml(elem, ns, {CODESYS_OBJECT_ID, CODESYS_ATTRIBUTES}, _DATA_TYPE_CHILDREN),
    )
    base = elem.find(_q(ns, "baseType"))
    if base is None:
        warnings.append(f"{name}: data type without baseType")
        return data_type
    data_type.base_type_xml = _canonical_xml(base)
    children = [child for child in base if isinstance(child.tag, str)]
    shape = _split(children[0].tag) if len(children) == 1 else ("", "")
    if shape == (ns, "struct"):
        data_type.kind = "struct"
        data_type.members = _parse_variables(
            children[0], ns, "struct", name, warnings, configuration, application,
        )
    elif shape == (ns, "enum"):
        data_type.kind = "enum"
        data_type.values = [
            EnumValue(name=value.get("name", ""), value=value.get("value"))
            for value in children[0].findall("/".join([_q(ns, "values"), _q(ns, "value")]))
        ]
        # CODESYS does not export the declared base type; only report one that is there.
        enum_base = children[0].find(_q(ns, "baseType"))
        if enum_base is not None:
            data_type.base_type = _type_name(enum_base, ns, f"{name} base type", warnings)
    else:
        data_type.base_type = _type_name(base, ns, f"{name} base type", warnings)
    return data_type


def _attributes(elem: Element, ns: str) -> list[Attribute]:
    """CODESYS pragmas from ``addData/data[@name=".../attributes"]/Attributes/Attribute``."""
    return [
        Attribute(name=attribute.get("Name", ""), value=attribute.get("Value", ""))
        for data in _data_elements(elem, ns, CODESYS_ATTRIBUTES)
        for attributes in data.findall(_q(ns, "Attributes"))
        for attribute in attributes.findall(_q(ns, "Attribute"))
    ]


def _residual_xml(
    elem: Element, ns: str, modelled_data: frozenset[str] | set[str], expected: frozenset[str],
) -> list[str]:
    """Canonical XML of what the parser does not interpret under *elem*.

    Direct ``addData/data`` children whose name is not modelled, plus any
    child element whose local name is not expected, in document order. Nested
    objectid data is stripped from the fragments (GUIDs are noise, Decision
    010); every other vendor detail stays.
    """
    residual = []
    for child in elem:
        if not isinstance(child.tag, str):
            continue
        namespace, local = _split(child.tag)
        if namespace == ns and local == "addData":
            for data in child:
                if not isinstance(data.tag, str):
                    continue
                if data.tag == _q(ns, "data") and data.get("name") in modelled_data:
                    continue
                residual.append(_canonical_xml(data, residual=True))
        elif namespace != ns or local not in expected:
            residual.append(_canonical_xml(child, residual=True))
    return residual


# --------------------------------------------------------------------------- #
# Parsing: POU, variables, body
# --------------------------------------------------------------------------- #


_POU_CHILDREN = frozenset({"interface", "actions", "body", "documentation", "addData"})
_ACTION_CHILDREN = frozenset({"body", "documentation", "addData"})
_METHOD_CHILDREN = frozenset({"interface", "body", "documentation", "addData"})
_PROPERTY_CHILDREN = frozenset(
    {"interface", "SetAccessor", "GetAccessor", "documentation", "addData"}
)
_OBJECT_ID_ONLY = frozenset({CODESYS_OBJECT_ID})


def _parse_pou(
    elem: Element, ns: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> Pou:
    name = elem.get("name", "")
    pou = Pou(
        name=name, pou_type=elem.get("pouType", ""),
        configuration=configuration, application=application,
        comment=_documentation(elem, ns),
        vendor_xml=_residual_xml(
            elem, ns, {CODESYS_OBJECT_ID, CODESYS_METHOD_DATA, CODESYS_PROPERTY_DATA}, _POU_CHILDREN,
        ),
    )
    interface = _parse_interface(elem, ns, name, warnings, configuration, application)
    pou.return_type, pou.return_type_xml = interface.return_type, interface.return_type_xml
    pou.variables, pou.interface_vendor_xml = interface.variables, interface.vendor_xml
    pou.comment = pou.comment or interface.comment
    body = elem.find(_q(ns, "body"))
    if body is not None:
        _parse_body(body, ns, pou)
    for actions in elem.findall(_q(ns, "actions")):
        for action in actions.findall(_q(ns, "action")):
            pou.actions.append(_parse_action(action, ns))
    for data in _data_elements(elem, ns, CODESYS_METHOD_DATA):
        for method in data.findall(_q(ns, "Method")):
            pou.methods.append(
                _parse_method(method, ns, name, warnings, configuration, application)
            )
    for data in _data_elements(elem, ns, CODESYS_PROPERTY_DATA):
        for prop in data.findall(_q(ns, "Property")):
            pou.properties.append(
                _parse_property(prop, ns, name, warnings, configuration, application)
            )
    return pou


class _Interface:
    """What an ``<interface>`` element contributes to its owner."""

    def __init__(self) -> None:
        self.return_type: str | None = None
        self.return_type_xml: str | None = None
        self.variables: list[Variable] = []
        self.vendor_xml: list[str] = []
        self.comment = ""


def _parse_interface(
    owner: Element, ns: str, scope: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> _Interface:
    """Parse ``owner/interface`` the same way for POUs, methods and accessors.

    *scope* is the scope path stored on every variable (``FB_Drive``,
    ``FB_Drive.M_Start``, ``FB_Drive.P_Speed.Get``).
    """
    result = _Interface()
    interface = owner.find(_q(ns, "interface"))
    if interface is None:
        return result
    result.comment = _documentation(interface, ns)
    for child in interface:
        if not isinstance(child.tag, str):
            continue
        namespace, local = _split(child.tag)
        if namespace == ns and local == "returnType":
            result.return_type = _type_name(child, ns, f"{scope} return type", warnings)
            result.return_type_xml = _canonical_xml(child)
        elif namespace == ns and local == "documentation":
            continue
        elif namespace == ns and local == "addData":
            result.vendor_xml.extend(_residual_xml(interface, ns, _OBJECT_ID_ONLY, frozenset(
                _local(other.tag) for other in interface if isinstance(other.tag, str)
            )))
        else:
            section = _section_name(local) if namespace == ns else None
            if section is None:
                warnings.append(f"{scope}: unknown interface element <{local}> skipped")
                result.vendor_xml.append(_canonical_xml(child, residual=True))
                continue
            if section not in KNOWN_SECTIONS:
                warnings.append(f"{scope}: unrecognised variable section <{local}>")
            result.variables.extend(_parse_variables(
                child, ns, section, scope, warnings, configuration, application,
            ))
    return result


def _parse_action(elem: Element, ns: str) -> Action:
    action = Action(
        name=elem.get("name", ""), comment=_documentation(elem, ns),
        vendor_xml=_residual_xml(elem, ns, _OBJECT_ID_ONLY, _ACTION_CHILDREN),
    )
    body = elem.find(_q(ns, "body"))
    if body is not None:
        _parse_body(body, ns, action)
    return action


def _parse_method(
    elem: Element, ns: str, pou_name: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> Method:
    scope = f"{pou_name}.{elem.get('name', '')}"
    interface = _parse_interface(elem, ns, scope, warnings, configuration, application)
    method = Method(
        name=elem.get("name", ""),
        return_type=interface.return_type, return_type_xml=interface.return_type_xml,
        variables=interface.variables,
        comment=_documentation(elem, ns) or interface.comment,
        interface_vendor_xml=interface.vendor_xml,
        vendor_xml=_residual_xml(elem, ns, _OBJECT_ID_ONLY, _METHOD_CHILDREN),
    )
    body = elem.find(_q(ns, "body"))
    if body is not None:
        _parse_body(body, ns, method)
    return method


def _parse_property(
    elem: Element, ns: str, pou_name: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> Property:
    name = elem.get("name", "")
    scope = f"{pou_name}.{name}"
    interface = _parse_interface(elem, ns, scope, warnings, configuration, application)
    if interface.variables:
        warnings.append(f"{scope}: variables declared on the property itself are ignored")
    prop = Property(
        name=name, type=interface.return_type, type_xml=interface.return_type_xml,
        comment=_documentation(elem, ns) or interface.comment,
        interface_vendor_xml=interface.vendor_xml,
        vendor_xml=_residual_xml(elem, ns, _OBJECT_ID_ONLY, _PROPERTY_CHILDREN),
    )
    for kind in ("Get", "Set"):
        accessor_elem = elem.find(_q(ns, f"{kind}Accessor"))
        if accessor_elem is not None:
            accessor = _parse_accessor(
                accessor_elem, ns, kind, f"{scope}.{kind}", warnings, configuration, application,
            )
            setattr(prop, "getter" if kind == "Get" else "setter", accessor)
    return prop


def _parse_accessor(
    elem: Element, ns: str, kind: str, scope: str, warnings: list[str],
    configuration: str | None, application: str | None,
) -> Accessor:
    interface = _parse_interface(elem, ns, scope, warnings, configuration, application)
    accessor = Accessor(
        kind=kind, variables=interface.variables, interface_vendor_xml=interface.vendor_xml,
        vendor_xml=_residual_xml(elem, ns, _OBJECT_ID_ONLY, _METHOD_CHILDREN),
    )
    body = elem.find(_q(ns, "body"))
    if body is not None:
        _parse_body(body, ns, accessor)
    return accessor


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


def _parse_body(body: Element, ns: str, pou: Pou | Action | Method | Accessor) -> None:
    """Fill the four body fields of any code unit (POU, action, method, accessor)."""
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


def _canonical_xml(elem: Element, *, graphical: bool = False, residual: bool = False) -> str:
    """Canonical XML with deterministic prefixes and lossless text content.

    Sorted namespace URIs receive ``n0``, ``n1``, ... independently of source
    prefixes, attribute order and ``ET.register_namespace``. C14N 2.0 sorts
    attributes. Only indentation in element-only content is removed, respecting
    inherited ``xml:space``; leaf and mixed-content text stays verbatim.
    Graphical bodies also lose the documented noise elements; residual vendor
    fragments lose only nested objectid data. The caller's tree is never
    modified and no Element escapes into the model.

    Assigning prefixes ourselves avoids CPython's prefix rewriter emitting
    invalid empty-namespace declarations next to unprefixed attributes.
    """
    fragment = _rebuild(elem, graphical, residual=residual)
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


def _object_id_noise(elem: Element) -> bool:
    """A CODESYS ``data[@name=".../objectid"]`` element (GUID noise, Decision 010)."""
    if not isinstance(elem.tag, str):
        return True
    namespace, local = _split(elem.tag)
    return (
        namespace.startswith(PLCOPEN_NS_PREFIX) and local == "data"
        and elem.get("name") == CODESYS_OBJECT_ID
    )


def _rebuild(
    elem: Element, graphical: bool, preserve_space: bool = False, residual: bool = False,
) -> Element:
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
        if isinstance(child.tag, str) and not (
            (graphical and _graphical_noise(child)) or (residual and _object_id_noise(child))
        ):
            copy.append(_rebuild(child, graphical, preserve_space, residual))
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
