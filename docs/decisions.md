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
- **M2.1 extension:** `samples/CHANGES_03_04.md` records the second pair, `03_line_large.xml` → `04_types_qualifiers.xml`.

## 005 — XML parsing goes through defusedxml
- **Decision:** The core library parses with `defusedxml.ElementTree`, the only runtime dependency. The elements it returns are plain `xml.etree` elements, so the rest of the parser is unchanged.
- **Why:** The web backend (M5) will parse files uploaded by strangers. `defusedxml` refuses entity expansion (billion laughs), external entities (XXE) and DTD retrieval, which the standard library parser happily follows.
- **Alternatives:** Plain `xml.etree` (unsafe on untrusted input); `lxml` (fast and safe when configured, but a compiled dependency that is not needed for files of this size).

## 006 — Variables carry their scope and section
- **Decision:** Every `Variable` stores `scope` (owning POU or GVL name) and `section` (`local`, `input`, `output`, `inout`, `global`, ...). Section names are derived generically from the `*Vars` tag name; unknown ones are still mapped and reported in `Project.warnings`.
- **Why:** The I/O table, the cross-reference (M3) and the diff (M4) all key a variable by `(scope, name)`. Storing it once at parse time keeps those modules free of tree walking, and the generic mapping means a new CODESYS section does not break parsing.
- **Alternatives:** Derive scope from ownership at query time (every consumer repeats the walk); a hard-coded list of sections (fails silently on anything new).
- **M2.1 amendment:** Decision 010 adds configuration/application ownership and replaces the variable key with `(application, scope, name)` within a configuration.

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
- **M2.1 amendment:** Decision 010 replaces project-wide name deduplication with deduplication of identical definitions within the same owner; conflicting definitions are retained.

## 010 — The parse model preserves comparison data (M2.1)
- **Decision:** The parse model must be lossless for everything M3/M4 may compare. A warning is not a substitute for keeping the data. Readable fields and structured nodes coexist with canonical XML for type declarations, initial values, return types and graphical bodies. Unknown type/value shapes and generic FBD/CFC details remain available without reparsing the source file.
- **Why:** M2 discarded ladder semantics, ownership, task target types, qualifiers and complex declaration details. Distinct source programs could therefore produce equal models, making correct cross-reference and version comparison impossible.
- **Ownership:** `Pou`, `GlobalVarList`, `Task` and `Variable` retain the enclosing configuration and application (the resource name). `None` means project/configuration scope, not an inferred application. Variable identity is `(configuration, application, scope, name)`. Deduplication compares POU definitions only within `(configuration, application, name)`. Identical copies collapse with a warning; conflicting definitions remain with a warning. Project POUs are independent of resource-local POUs.
- **Tasks and graphical bodies:** A task stores `PouInstance(instance_name, type_name)`; empty `typeName` falls back to the instance name. LD instructions retain kind, local ID, variable, negation, storage, edge and incoming connection IDs. Canonical instruction/body XML preserves other graph semantics, including generic FBD/CFC and vendor content. Local IDs are strings, preserving the XML identifiers without numeric coercion.
- **Declarations:** Recursive arrays and sized STRING/WSTRING types have readable names; `derived_types` exposes derived bases even inside arrays. The readable fields (`Variable.type`, `Variable.initial_value`, `Pou.return_type`) never contain XML: array and struct initial values show `(array)` / `(struct)`, types without a short form show `(struct)` / `(unknown)`, and an unknown leaf type tag shows its own name with a warning. Canonical `type_xml` / `initial_value_xml` / `return_type_xml` carry the full detail and distinguish declarations whose readable forms coincide. The model contains strings and dataclasses, never live XML elements.
- **Qualifiers:** Each variable stores `retain`, `nonretain`, `persistent` and `constant`, defaulting to false. For CODESYS mixed global lists, the top-level variables supply declarations and `MixedAttrsVarList` supplies the complete qualifier set by variable name. Nested lists never become extra GVLs. Sample 04 is the real-format reference.
- **Normalization (M2.3):** Canonical fragments use C14N 2.0 after assigning `n0`, `n1`, ... to the fragment's sorted namespace URIs. The empty namespace remains unprefixed and the reserved XML namespace keeps `xml`. Prefix numbering is independent of source prefixes, attribute order and the process-wide `ElementTree.register_namespace` state. C14N sorts attributes and uses canonical XML escaping and explicit end tags. Indentation is removed only from pure element content: the parent has element children and neither its text nor any child tail contains non-whitespace text. Here whitespace means XML whitespace (space, tab, CR and LF). An effective `xml:space="preserve"` keeps that indentation too; it is inherited within the fragment until `xml:space="default"` resets it. A child's tail follows its parent's setting. All other parsed text is preserved verbatim, including leading/trailing/internal whitespace, mixed content and whitespace-only leaves. This preserves text content, not source spellings such as CDATA or entity references; XML parsing already normalizes source line endings. The fragment root's tail belongs to its surrounding document and is excluded.
- **Documented exclusions:** GUIDs, timestamps, device/library metadata, XML comments, graphical positions, LD network comments and CODESYS network titles remain excluded. Unknown vendor elements are preserved, even when their local names resemble layout tags; excluding an element does not discard its tail text. ST text retains whitespace apart from normalized line endings. M4 must choose semantic fields rather than compare project headers or diagnostics.
- **Alternatives:** Warning-only fallback (loses evidence); retaining only the original file (forces every consumer to parse XML); storing live ElementTree objects (poor JSON boundary and mutable shared state); deduplicating all equal names (merges different applications).
- **Revised in M2.2:** the first version let canonical XML depend on registered prefixes and put XML into the readable fields, which broke the `plcdoc parse` table. Fixed as described above; `is_derived` was dropped in favour of `derived_types`; `Task.settings` (CODESYS TaskSettings) and `Pou.comment` are kept. Still deferred to M3: `ProjectStructure`, `types/dataTypes`, POU methods/actions in `pou/addData`, and unifying the two ownership walks.
- **Revised in M2.3:** canonicalization preserves significant text and numbers prefixes by sorted URI, fixing M2.2's text stripping and attribute-order dependence. The CLI table is plain terminal output: only pipes are escaped and newlines replaced with spaces. This supersedes decision 008's proposed reuse for rendered Markdown; export escaping and rendered-text tests belong to M3.
