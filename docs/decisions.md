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
