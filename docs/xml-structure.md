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
│   │   │   └── pouInstance name = instance; typeName = POU type (empty here)
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

M2.1 preserves structured instructions (kind, local ID, variable, negation,
storage, edge and incoming connection IDs), plus canonical XML for other body
details. M3 can use contact/coil variables for cross-reference; M4 can detect
wiring or instruction changes. FBD/CFC use the same generic preservation path;
they have synthetic coverage, but no real export is available yet. No diagram
rendering is attempted.

## Findings from `samples/04_types_qualifiers.xml`
Same project as sample 03, plus a second global list `GVL_Extra` and two array variables in `PLC_PRG`.
Sample 03 → 04 is therefore also a realistic "upgrade" pair for diff tests.

### Arrays, strings, array initial values
```xml
<type>
  <array>
    <dimension lower="1" upper="4" />
    <baseType><REAL /></baseType>              <!-- or <derived name="FB_Motor" /> -->
  </array>
</type>
<type><string length="20" /></type>            <!-- STRING(20) -->
<initialValue>
  <arrayValue>
    <value><simpleValue value="10" /></value>
    <value><simpleValue value="20" /></value>
  </arrayValue>
</initialValue>
```
- `aSpare : ARRAY[1..2] OF FB_Motor` is an array of FB instances: the program tree must look inside `array/baseType`.
- Exact readable types in sample 04: `aTemps` is `ARRAY[1..4] OF REAL`,
  `sRecipeName` is `STRING(20)`, `aSetpoints` is `ARRAY[1..3] OF INT`, and
  `aSpare` is `ARRAY[1..2] OF FB_Motor`. `aSetpoints` has initial values 10, 20, 30.
- Nested/multidimensional arrays and `wstring length="n"` → `WSTRING(n)` have
  synthetic regression coverage; they are not present in sample 04.
- `type_xml` and `initial_value_xml` preserve canonical declaration details.
  The readable fields never contain XML: a compound initializer shows `(array)`
  or `(struct)`, a type without a short form shows `(struct)` or `(unknown)`, and
  an unknown leaf type tag shows its tag name with a warning.

### RETAIN / CONSTANT in a global list (important)
`GVL_Extra` declares three blocks: `VAR_GLOBAL`, `VAR_GLOBAL RETAIN`, `VAR_GLOBAL CONSTANT`.
CODESYS exports it as:
- **one** top-level `globalVars name="GVL_Extra"` holding all four variables, **without** any `retain`/`constant` attribute;
- the real split is only inside
  `globalVars/addData/data[@name="http://www.3s-software.com/plcopenxml/mixedattrsvarlist"]/MixedAttrsVarList`,
  which contains several `globalVars name="GVL_Extra"` elements, each with its own `retain="true"` or `constant="true"`.

Consequences for the parser:
- Read the variable list from the top-level `globalVars`, then take qualifiers from `MixedAttrsVarList` when present.
  Reading only the top level loses RETAIN and CONSTANT without any error.
- The nested `globalVars` inside `MixedAttrsVarList` are **not** separate lists. The file has 5 `globalVars` elements but only 2 real lists.
- A list with a single block (`GVL_IO`) has no `MixedAttrsVarList`.
- Expected qualifiers: `diTotalCount` is RETAIN; `MAX_ZONES` is CONSTANT;
  `aTemps`, `sRecipeName` and all of `GVL_IO` have none. NONRETAIN and PERSISTENT
  use the same attribute handling, with synthetic coverage.
- Sample 04 has exactly 2 GVLs, 4 POUs, 42 variables and 20 addressed variables.
  The complete second diff-pair expectation is in `samples/CHANGES_03_04.md`.

## Ownership and task bindings (M2.1)

- All four real exports have `configuration name="Device"` and
  `resource name="Application"`. These names are retained on POUs, GVLs, tasks
  and variables. Project-level objects have no configuration/application;
  configuration-level GVLs have a configuration but no application.
- Variable identity is `(configuration, application, scope, name)`.
  Identical same-name POUs deduplicate only within the same owner. Definitions
  in different resources or at project scope remain independent. Conflicting
  definitions within one owner are preserved with a warning.
- All sample task instances use `name="PLC_PRG" typeName=""`. Store both the
  instance name and resolved type name, falling back to `name` when `typeName`
  is empty. Separate instance/type names and multiple owners have synthetic tests.
- `task/addData/data[@name=".../tasksettings"]/TaskSettings` holds the task kind,
  interval text and watchdog. Kept flattened in `Task.settings`
  (`KindOfTask`, `Interval`, `Watchdog.Enabled`, ...).
- `pou/documentation` (or `interface/documentation`) is the POU comment, kept in
  `Pou.comment`. No sample POU has one.
- POU-interface `globalVars` belongs to that POU. Only direct
  configuration/resource `globalVars` is a project GVL.

## Useful extras
- `task`: task name, cycle (`interval="PT0.02S"`), priority, and which program it calls → program tree.
- `ProjectStructure`: object hierarchy with names → program tree.
- `fileHeader/@productVersion`: shown in generated docs.

## Noise to ignore (especially in diff)
- `ObjectId` GUIDs
- `creationDateTime`, `modificationDateTime`
- `Libraries`, `Device` description, `coordinateInfo`
- Line-ending differences inside code bodies (normalize before comparing)
