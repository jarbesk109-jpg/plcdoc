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
│   │       ├── data[@name=".../plcopenxml/datatype"]   → dataType  ← DUTs (sample 05)
│   │       ├── data[@name=".../plcopenxml/pou"]        → pou  ← the actual program
│   │       └── data[@name=".../plcopenxml/libraries"]  → Libraries
│   └── addData             Device description (ignore)
└── addData
    └── data[@name=".../plcopenxml/projectstructure"]  → ProjectStructure (object tree)
```

## Where POUs live
In samples 01–05, which include the Device, CODESYS puts POUs **inside the resource's `addData`**,
not in `types/pous`. The standard location `types/pous` is empty in those files;
sample 06 also has a project-level POU there (see its findings below).
The parser must look in **both** places:
1. `types/pous/pou`
2. `.../resource/addData/data[@name="http://www.3s-software.com/plcopenxml/pou"]/pou`

DUTs follow the same rule (see sample 05 findings).

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
- POU-interface `globalVars` belongs to that POU. Samples 01–04 have their GVLs
  directly under the resource; sample 06 adds a project-level GVL in `addData`.

## Findings from `samples/05_drive_oop.xml`
New project (not a version of 01–04): ENUM `E_DriveState`, STRUCT `ST_Drive`,
FB `FB_Drive` with method `M_Start`, action `A_Reset`, property `P_Speed`
(Get/Set), and `PLC_PRG` using all of them. Exported the same way as the other
samples (Device included).

### Where DUTs live
Same rule as POUs: `types/dataTypes` is empty. Each DUT is in its own wrapper:
`.../resource/addData/data[@name="http://www.3s-software.com/plcopenxml/datatype"]/dataType`.

All vendor elements below (`Method`, `Property`, `SetAccessor`, `GetAccessor`,
`Attributes`, `ProjectStructure`) are in the **PLCopen default namespace**, not
in the vendor URI. Lookups must use `tc6_0200`.

### ENUM
```xml
<dataType name="E_DriveState">
  <baseType>
    <enum>
      <values>
        <value name="IDLE" value="0" />
        <value name="RUNNING" value="10" />
        <value name="FAULT" value="99" />
      </values>
    </enum>
  </baseType>
  <addData>
    <data name=".../plcopenxml/attributes">
      <Attributes>
        <Attribute Name="qualified_only" Value="" />
        <Attribute Name="strict" Value="" />
      </Attributes>
    </data>
    <data name=".../plcopenxml/objectid"> ... </data>
  </addData>
</dataType>
```
- Explicit values are in `value/@value` (string).
- **The declared base type is lost.** The source says `) INT;`, but `INT` does
  not appear anywhere in the file. The parser must not invent a default; report
  the base type as not exported.
- `{attribute '...'}` pragmas become `Attribute` elements (`Name`, `Value`) in
  declaration order. A flag pragma has `Value=""`.

### STRUCT
Standard PLCopen: `baseType/struct/variable`, same `variable` format as POU
interfaces (arrays and `string length` as in sample 04).
- A field of another DUT type: `<derived name="E_DriveState" />`.
- An enum initial value is qualified text: `<simpleValue value="E_DriveState.IDLE" />`.
- No pragmas were declared, so the STRUCT has only the `objectid` data.

### Function block members
Child order of `pou[@name="FB_Drive"]`: `interface`, `actions`, `body`, `addData`.

**Action: standard PLCopen**, placed before the FB `body`:
```xml
<actions>
  <action name="A_Reset">
    <body><ST><xhtml>...</xhtml></ST></body>
    <addData><data name=".../plcopenxml/objectid"> ... </data></addData>
  </action>
</actions>
```
No interface: actions have no own variables.

**Method: vendor data** in the FB `addData`:
```xml
<data name=".../plcopenxml/method" handleUnknown="implementation">
  <Method name="M_Start" ObjectId="...">
    <interface>
      <returnType><BOOL /></returnType>
      <inputVars> ... </inputVars>
      <localVars> ... </localVars>
    </interface>
    <body><ST><xhtml>...</xhtml></ST></body>
    <addData />
  </Method>
</data>
```

**Property: vendor data** in the FB `addData`:
```xml
<data name=".../plcopenxml/property" handleUnknown="implementation">
  <Property name="P_Speed" ObjectId="...">
    <interface>
      <returnType><REAL /></returnType>
      <addData>
        <data name=".../plcopenxml/accessmodifiers"><AccessModifiers /></data>
      </addData>
    </interface>
    <SetAccessor>
      <interface />
      <body><ST><xhtml>rSpeed := P_Speed;</xhtml></ST></body>
      <addData />
    </SetAccessor>
    <GetAccessor>
      <interface />
      <body><ST><xhtml> P_Speed := rSpeed;</xhtml></ST></body>
      <addData />
    </GetAccessor>
    <addData />
  </Property>
</data>
```
- `SetAccessor` comes **before** `GetAccessor`. Do not assume order.
- Each accessor has its own (here empty) `interface`.
- `AccessModifiers` is empty when no modifier (PUBLIC, PRIVATE, ...) is set.
- FB `addData` order in this file: `method`, `property`, `objectid`.

### Code body whitespace
The Get body is `" P_Speed := rSpeed;"` with a leading space typed in the
editor. Unlike variable comments, code text is **not** stripped: this is real
content and must be preserved (Decision 010).

### ObjectId locations
| Object | Where the ObjectId is |
|---|---|
| dataType, pou, action, task, Libraries, resource, configuration | `addData/data[@name=".../objectid"]/ObjectId` |
| Method, Property | `@ObjectId` attribute |
| Get/Set accessors | none |

### ProjectStructure
Under the project-level `addData`:
```xml
<ProjectStructure>
  <Object Name="Device" ObjectId="...">
    <Object Name="Application" ObjectId="...">
      <Object Name="Library Manager" ObjectId="..." />
      <Object Name="PLC_PRG" ObjectId="..." />
      <Object Name="MainTask" ObjectId="..." />
      <Object Name="E_DriveState" ObjectId="..." />
      <Object Name="ST_Drive" ObjectId="..." />
      <Object Name="FB_Drive" ObjectId="...">
        <Object Name="M_Start" ObjectId="..." />
        <Object Name="A_Reset" ObjectId="..." />
        <Object Name="P_Speed" ObjectId="..." />
      </Object>
    </Object>
  </Object>
</ProjectStructure>
```
- Only `Name` and `ObjectId`: **no object kind**. The kind comes from joining
  the ObjectId with the table above.
- Order differs from the CODESYS tree view.
- `Task Configuration` is not a node; `MainTask` sits directly under `Application`.
- Get/Set accessors are not nodes.

### Notes for cross-reference (M3a)
- Same name, different scope: `xOk` is a local of both `PLC_PRG` and `FB_Drive.M_Start`.
- Method bodies use FB members (`stData`) without a prefix: resolve method
  variables first, then FB variables.
- `M_Start := xOk;` assigns the method return value, not a variable.
- In the Set accessor, `P_Speed` is the incoming value.
- `fbDrive.P_Speed := 1200.0;` is a property write (calls Set);
  `rActual := fbDrive.P_Speed;` is a property read (calls Get).
- `E_DriveState.RUNNING` is an enum literal, not a variable.

### How M3a reads it (implemented, Decisions 011/012)
- Scope paths: `FB_Drive.M_Start` (method), `FB_Drive.A_Reset` (action),
  `FB_Drive.P_Speed.Get` / `.Set` (accessors) are the `Variable.scope` of
  member variables and the `unit` of cross-reference locations.
- `plcdoc.xref.cross_reference` yields exactly 29 references for this sample
  (12 in `PLC_PRG`, 3 in the FB body, 2 in `A_Reset`, 8 in `M_Start`, 2 per
  accessor), nothing unresolved, no warnings; the full list is the oracle in
  `tests/test_xref.py`.
- `AccessModifiers` is kept as canonical XML in `Property.interface_vendor_xml`;
  the enum base type stays `None`; ObjectIds are used only to label
  `Project.structure` and are not stored.
- Nothing new about the XML shape turned up during implementation; the
  findings above were sufficient.

### Ladder bodies in the cross-reference
Sample 03's `PRG_Alarm` yields two references located by `localId`: contact
`3` reads `GVL_IO.bDoorClosed`, coil `4` writes `GVL_IO.bHorn`. Blocks
(`block[@instanceName]` with `inputVariables` / `outputVariables` /
`inOutVariables` pins) and `inVariable` boxes now have a real example in sample
06 below. The existing synthetic tests also cover `outVariable` boxes and
block-to-block wiring.

## Findings from `samples/06_ld_pool.xml`

The file header identifies CODESYS V3.5 SP22 Patch 3. This export contains
project-level objects as well as `Device` / `Application` objects.

### Project-level GVL and POU
- `GVL_Pool` is at
  `project/addData/data[@name="http://www.3s-software.com/plcopenxml/globalvars"]/globalVars`.
  Its direct variables are `gPoolCount : INT` and `gPoolFlag : BOOL`.
- `FB_PoolUser` is at `project/types/pous/pou`, with `pouType="functionBlock"`.
  Its `interface/externalVars` declares `gPoolCount : INT`, and
  `interface/outputVars` declares `xFlagSeen : BOOL`. Its ST body is:
  ```st
  gPoolCount := gPoolCount + 1;
  xFlagSeen := GVL_Pool.gPoolFlag;
  ```
- Neither object is enclosed by a configuration or resource. In
  `ProjectStructure`, both are siblings of `Device`, outside `Application`.
- `PLC_PRG` and `PRG_Ladder` are in the Application resource's `addData`, each
  inside a `data[@name="http://www.3s-software.com/plcopenxml/pou"]` wrapper.
  `PLC_PRG` calls `PRG_Ladder()` and `fbPool()` and contains
  `IF (bHorn S= bDoorClosed) THEN bLampRun := TRUE; END_IF;`.

### Real LD block and pins
`PRG_Ladder/body/LD` contains these PLCopen-namespaced elements:
- Contact `localId="4"` reads the `variable` text `xStart` and is connected to
  left power rail `0`.
- `inVariable localId="5"` contains `expression` text `T#2S`.
- `block localId="3" typeName="TON" instanceName="tonDelay"` has
  `inputVariables/variable` pins `IN` and `PT`. Their
  `connectionPointIn/connection/@refLocalId` values are `4` and `5` respectively;
  neither input pin has an inline expression in this file.
- Its `inOutVariables` is empty. The `outputVariables/variable` pins are `Q`
  and `ET`. `Q/connectionPointOut` is empty, while the ET pin contains:
  ```xml
  <variable formalParameter="ET">
    <connectionPointOut>
      <expression>tElapsed</expression>
    </connectionPointOut>
  </variable>
  ```
- Coil `localId="6"` contains `variable` text `xDone`; its incoming connection
  has `refLocalId="3" formalParameter="Q"`.
- The TON block's `addData` contains `fbdcalltype/CallType` text `functionblock`,
  `inputparamtypes/InputParamTypes` text `BOOL TIME`, and empty
  `outputparamtypes/OutputParamTypes`. These three payload elements reset their
  namespace with `xmlns=""`.

### Real Execute box and known issue
The second network has contact `localId="10"` with variable `xDone`, followed
by **`block localId="9" typeName="EXECUTE"`**, with no `instanceName`.
Its input pin `EN` connects to contact `10`; output pin `ENO` has an empty
`connectionPointOut`, and `inOutVariables` is empty.

The block's PLCopen-namespaced `addData/data` wrappers contain:
- `name="http://www.3s-software.com/plcopenxml/fbdcalltype"` with
  `<CallType xmlns="">execute</CallType>`;
- `name="http://www.3s-software.com/plcopenxml/inputparamtypes"` with
  `<InputParamTypes xmlns="">BOOL</InputParamTypes>`;
- `name="http://www.3s-software.com/plcopenxml/outputparamtypes"` with an empty
  `<OutputParamTypes xmlns="" />`;
- `name="http://www.3s-software.com/plcopenxml/stcode"` with unqualified
  `STCode`, whose text has three leading spaces on each line and a trailing LF:
  ```text
     iCount := iCount + 1;
     xLamp := xDone AND xStart;
  ```

**Known issue:** the Execute payload is not cross-referenced yet. The existing
synthetic Execute fixtures use a `vendorElement` with an `fbdelementtype`
marker; they model a shape this SP22 export does not produce. In this file,
the `vendorElement` markers are `networktitle`, while Execute is the block
described above. Payload cross-referencing needs its own implementation plan.

## Useful extras
- `task`: task name, cycle (`interval="PT0.02S"`), priority, and which program it calls → program tree.
- `ProjectStructure`: object hierarchy with names → program tree (details and caveats in sample 05 findings).
- `fileHeader/@productVersion`: shown in generated docs.

## Noise to ignore (especially in diff)
- `ObjectId` GUIDs (ignore when comparing, but needed to join `ProjectStructure` nodes to objects)
- `creationDateTime`, `modificationDateTime`
- `Libraries`, `Device` description, `coordinateInfo`
- Line-ending differences inside code bodies (normalize before comparing)
