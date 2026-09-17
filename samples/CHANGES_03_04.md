# Expected changes: 03_line_large.xml → 04_types_qualifiers.xml

Second ground-truth pair for M4. Both exports use `Device/Application`.
M2.1 tests establish these differences at the parse-model boundary; the diff
command itself belongs to M4.

## Added global variable list

`GVL_Extra` is added with four variables:

| Variable | Type | Initial value | Qualifiers | Comment |
|---|---|---|---|---|
| `aTemps` | `ARRAY[1..4] OF REAL` | absent | none | Nhiệt độ 4 vùng |
| `sRecipeName` | `STRING(20)` | absent | none | Tên công thức |
| `diTotalCount` | `DINT` | absent | RETAIN | Tổng sản phẩm, nhớ khi mất điện |
| `MAX_ZONES` | `INT` | `4` | CONSTANT | Số vùng gia nhiệt |

The three nested `globalVars` blocks in `MixedAttrsVarList` describe qualifiers
for these same four variables. They are not additional GVLs or declarations.

## Added variables in PLC_PRG

| Variable | Section | Type | Initial value | Comment |
|---|---|---|---|---|
| `aSetpoints` | local | `ARRAY[1..3] OF INT` | `[10, 20, 30]` | Điểm đặt |
| `aSpare` | local | `ARRAY[1..2] OF FB_Motor` | absent | Băng tải dự phòng |

Neither variable has an address or a qualifier. `initial_value` shows the
placeholder `(array)`; the values live in `initial_value_xml`. The bracket
notation above is explanatory.

## Unchanged / ignored

- All 36 existing variables, including every declaration in `GVL_IO`, are unchanged.
- No POU is added or removed. Existing ST bodies, the `PRG_Alarm` LD body and task bindings are unchanged.
- There are still 20 addressed variables. Total variables increase from 36 to 42; real GVLs increase from one to two.
- Ignore export filenames, timestamps, ObjectId GUIDs, device/library metadata and project-structure bookkeeping, as in the first diff pair.
