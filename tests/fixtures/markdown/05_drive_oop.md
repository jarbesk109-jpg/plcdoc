# 05\_drive\_oop\.project

- Product\: CODESYS V3\.5 SP22 Patch 3
- POUs\: PLC\_PRG\, FB\_Drive
- Global variable lists\: none

## I\/O table \(0\)

| Address | Direction | Name | Type | Scope | Comment |
|---------|-----------|------|------|-------|---------|

## Variables \(10\)

| Scope               | Section | Name     | Type      | Address | Initial | Comment |
|---------------------|---------|----------|-----------|---------|---------|---------|
| PLC\_PRG            | local   | fbDrive  | FB\_Drive |         |         |         |
| PLC\_PRG            | local   | xStart   | BOOL      |         |         |         |
| PLC\_PRG            | local   | xOk      | BOOL      |         |         |         |
| PLC\_PRG            | local   | rActual  | REAL      |         |         |         |
| FB\_Drive           | input   | xEnable  | BOOL      |         |         |         |
| FB\_Drive           | output  | xRunning | BOOL      |         |         |         |
| FB\_Drive           | local   | stData   | ST\_Drive |         |         |         |
| FB\_Drive           | local   | rSpeed   | REAL      |         |         |         |
| FB\_Drive\.M\_Start | input   | rTarget  | REAL      |         |         |         |
| FB\_Drive\.M\_Start | local   | xOk      | BOOL      |         |         |         |
