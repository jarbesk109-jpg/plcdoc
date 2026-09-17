# PLCopen XML structure (CODESYS export)

Notes from a real export: `samples/01_conveyor_v1.xml`
(CODESYS V3.5 SP22 Patch 3, whole project exported: Device, Application, Library Manager, MainTask, PLC_PRG).

## File-level facts
- Encoding: UTF-8 **with BOM**. Line endings are mixed: CRLF in the XML, LF inside code bodies.
- Default namespace: `http://www.plcopen.org/xml/tc6_0200`. Every tag lookup must use it.
- Comments and code text live in a second namespace: `http://www.w3.org/1999/xhtml`.
- The `Device` element resets the namespace to empty (`xmlns=""`).
- Special characters in code are escaped (`=>` is stored as `=&gt;`). An XML parser unescapes them automatically.

## Skeleton
```
project
├── fileHeader              productName, productVersion, creationDateTime
├── contentHeader           name = project file name, modificationDateTime
├── types
│   ├── dataTypes           (empty here)
│   └── pous                (EMPTY here — see "Where POUs live")
├── instances/configurations/configuration[@name=Device]
│   ├── resource[@name=Application]
│   │   ├── task            name, interval, priority
│   │   │   └── pouInstance name = program called by this task
│   │   └── addData
│   │       ├── data[@name=".../plcopenxml/pou"]        → pou  ← the actual program
│   │       └── data[@name=".../plcopenxml/libraries"]  → Libraries
│   └── addData             Device description (ignore)
└── addData
    └── data[@name=".../plcopenxml/projectstructure"]  → ProjectStructure (object tree)
```

## Where POUs live
When the Device is included in the export, CODESYS puts POUs **inside the resource's `addData`**,
not in `types/pous`. The standard location `types/pous` is empty.
The parser must look in **both** places:
1. `types/pous/pou`
2. `.../resource/addData/data[@name="http://www.3s-software.com/plcopenxml/pou"]/pou`

## POU
```xml
<pou name="PLC_PRG" pouType="program">
  <interface>
    <localVars>
      <variable name="..." address="%IX0.0"> ... </variable>
    </localVars>
  </interface>
  <body>
    <ST><xhtml>...code text...</xhtml></ST>
  </body>
</pou>
```
- `pouType`: `program` here. Expect `functionBlock` and `function` in larger files.
- Only `localVars` appear in this file. Expect `inputVars`, `outputVars`, `inOutVars`, `globalVars` elsewhere.

## Variable
| Information | Where | Example |
|---|---|---|
| Name | `@name` | `bStart` |
| I/O address | `@address` (missing if not mapped) | `%IX0.0` |
| Elementary type | child tag name inside `type` | `<BOOL />` → `BOOL` |
| Derived type (FB instance) | `type/derived/@name` | `CTU` |
| Initial value | `initialValue/simpleValue/@value` | `10` |
| Comment | `documentation/xhtml` text | ` Nút Start (NO)` |

- Address prefix gives the I/O direction: `%I` input, `%Q` output, `%M` memory.
- Comment text starts with a space. Strip it.

## Comment attribution (lossy)
CODESYS converts `//` comments in the declaration into per-variable documentation:
- A comment **on the same line** as a variable becomes its documentation.
- A comment **on its own line** is attached to the next variable only if that variable has no same-line comment.
  In this file, `// Internal` became the documentation of `fbCounter`.
- Section headers such as `// Inputs` and `// Outputs` are otherwise **lost**.

Consequence: comments are useful for the I/O table but are not a reliable source of grouping.

## Findings from `samples/03_line_large.xml`
Larger export: a global variable list, a function block, a function and a ladder program.

### POU types and variable sections
- `pouType` values seen: `program`, `functionBlock`, `function`.
- Variable sections seen inside `interface`: `localVars`, `inputVars`, `outputVars`.
- A function has its return type in `interface/returnType` (e.g. `<REAL />`).
- FB instances are variables whose type is `derived` (`fbConv1 : FB_Motor`, `tonFault : TON`).
  This is how the program tree links a program to the blocks it uses.
- All four POUs are again inside the resource's `addData`; `types/pous` is still empty.

### Global variable list
- Location: `instances/configurations/configuration/resource/globalVars[@name="GVL_IO"]`.
  It sits directly under `resource`, **not** inside `addData`.
- `@name` is the list name as shown in CODESYS.
- Same `variable` format as POU variables. Seen addresses: `%IX`, `%QX`, `%IW`, `%QW`, `%MX`.
  Most I/O in real projects lives here, so the I/O table must read global variables, not only POU variables.

### Ladder (LD) body
`body/LD` is a graph, not text:
- `leftPowerRail`, `rightPowerRail`
- `contact`: `@negated="true"` for a normally-closed contact, variable name in the child `variable` text
- `coil`: same pattern, also has `@storage` (set/reset)
- Wiring: `connectionPointIn/connection/@refLocalId` points to the `@localId` of the previous element
- Also contains an XML comment (`<!--ObjectVersion: LD1-->`), a network `comment` and a `vendorElement` (network title). Ignore them.
- All `position` values are `0,0`: CODESYS does not export layout, so a drawing cannot be rebuilt from positions.

For the first version: collect the variable names used by contacts and coils (cross-reference),
and do not try to render ladder diagrams.

## Useful extras
- `task`: task name, cycle (`interval="PT0.02S"`), priority, and which program it calls → program tree.
- `ProjectStructure`: object hierarchy with names → program tree.
- `fileHeader/@productVersion`: shown in generated docs.

## Noise to ignore (especially in diff)
- `ObjectId` GUIDs
- `creationDateTime`, `modificationDateTime`
- `Libraries`, `Device` description, `coordinateInfo`
- Line-ending differences inside code bodies (normalize before comparing)
