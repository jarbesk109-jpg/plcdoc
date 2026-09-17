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

## Useful extras
- `task`: task name, cycle (`interval="PT0.02S"`), priority, and which program it calls → program tree.
- `ProjectStructure`: object hierarchy with names → program tree.
- `fileHeader/@productVersion`: shown in generated docs.

## Noise to ignore (especially in diff)
- `ObjectId` GUIDs
- `creationDateTime`, `modificationDateTime`
- `Libraries`, `Device` description, `coordinateInfo`
- Line-ending differences inside code bodies (normalize before comparing)
