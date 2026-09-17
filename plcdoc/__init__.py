"""PLCdoc - documentation and version diff for PLC projects (PLCopen XML)."""

from plcdoc.model import (
    Address,
    GlobalVarList,
    Pou,
    Project,
    Task,
    Variable,
    parse_address,
)
from plcdoc.parser import ParseError, parse_bytes, parse_file, parse_string

__version__ = "0.0.1"

__all__ = [
    "Address",
    "GlobalVarList",
    "ParseError",
    "Pou",
    "Project",
    "Task",
    "Variable",
    "__version__",
    "parse_address",
    "parse_bytes",
    "parse_file",
    "parse_string",
]
