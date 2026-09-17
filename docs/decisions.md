# Decisions

Short records of technical decisions: what was decided, why, and what else was considered.

## 001 — Input format: PLCopen XML
- **Decision:** Read PLCopen XML exports, not vendor project files.
- **Why:** An open, documented exchange format supported by CODESYS and many other IDEs. No reverse-engineering of proprietary formats.
- **Alternatives:** Parsing vendor project files directly (closed, version-dependent).

## 002 — Three layers: core library, API, web UI
- **Decision:** `plcdoc` core library (also published to PyPI) → FastAPI backend → React frontend.
- **Why:** The core works from the command line without the web app and can be tested in isolation.

## 003 — Positioning
- **Decision:** PLCdoc does not try to replace commercial tools such as Copia, VersionDog or Siemens VCI.
- **Why:** It aims to be the open, free, no-install option for students, small shops and small integrators.

## 004 — Sample files as ground truth
- **Decision:** `samples/` holds real CODESYS exports. `samples/CHANGES_v1_v2.md` lists every intentional change between v1 and v2 and is the expected output for diff tests.
- **Why:** Tests run against real data with a known answer.

## 005 — XML parsing goes through defusedxml
- **Decision:** The core library parses with `defusedxml.ElementTree`, the only runtime dependency. The elements it returns are plain `xml.etree` elements, so the rest of the parser is unchanged.
- **Why:** The web backend (M5) will parse files uploaded by strangers. `defusedxml` refuses entity expansion (billion laughs), external entities (XXE) and DTD retrieval, which the standard library parser happily follows.
- **Alternatives:** Plain `xml.etree` (unsafe on untrusted input); `lxml` (fast and safe when configured, but a compiled dependency that is not needed for files of this size).

## 006 — Variables carry their scope and section
- **Decision:** Every `Variable` stores `scope` (owning POU or GVL name) and `section` (`local`, `input`, `output`, `inout`, `global`, ...). Section names are derived generically from the `*Vars` tag name; unknown ones are still mapped and reported in `Project.warnings`.
- **Why:** The I/O table, the cross-reference (M3) and the diff (M4) all key a variable by `(scope, name)`. Storing it once at parse time keeps those modules free of tree walking, and the generic mapping means a new CODESYS section does not break parsing.
- **Alternatives:** Derive scope from ownership at query time (every consumer repeats the walk); a hard-coded list of sections (fails silently on anything new).

## 007 — Natural address ordering
- **Decision:** `parse_address` splits `%IX0.7` into `(area, size, path)` and the I/O table sorts by area (I, Q, M), then size (X, B, W, D, L), then the numeric path. `%IX1.0` therefore follows `%IX0.7` and `%IX0.10` follows `%IX0.2`. Unparseable addresses go last in string order.
- **Why:** String order puts `%IX0.10` before `%IX0.2` and `%IX1.0` before `%IX0.7`, which is unreadable in an I/O table.
- **Alternatives:** Document order (depends on how the author declared things); pure string order.

## 008 — CLI prints Markdown tables; JSON output is deterministic
- **Decision:** `plcdoc parse` prints Markdown tables (reused by the M3 Markdown export). `plcdoc parse --json` dumps the `Project` dataclasses with sorted keys, parse-order lists and unescaped UTF-8.
- **Why:** Readable in a terminal without extra dependencies. Deterministic JSON lets tests and the M4 diff compare outputs byte for byte, and M5 can return the same structure from the API.
- **Alternatives:** `rich`/`tabulate` for prettier tables (extra dependencies); YAML output.

## 009 — POU discovery covers three locations
- **Decision:** POUs are read from `types/pous/pou` first and then from every CODESYS `data[@name=".../plcopenxml/pou"]` element; the first POU with a given name wins and duplicates are reported. Global variable lists are read only from `configuration/globalVars` and `resource/globalVars`, never from inside a POU interface. Discovery and parsing are separate functions, so a variable is parsed the same way wherever it sits.
- **Why:** CODESYS leaves the standard location empty when the Device is exported (see `docs/xml-structure.md`), and a `globalVars` section is also a legal POU interface section.
- **Alternatives:** Only the CODESYS location (breaks on other tools' exports); a whole-tree search for `globalVars` (would turn POU-level sections into GVLs).
