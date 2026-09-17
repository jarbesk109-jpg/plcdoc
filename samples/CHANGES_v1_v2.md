# Expected changes: 01_conveyor_v1.xml → 02_conveyor_v2.xml

Ground truth for diff tests. Everything listed here must be reported.
Everything not listed here must NOT be reported.

POU: `PLC_PRG` (program). Same ObjectId in both files.

## Variables
| # | Change | Variable | v1 | v2 |
|---|--------|----------|----|----|
| 1 | Initial value changed | `iPreset` | `10` | `20` |
| 2 | Address changed | `bLampDone` | `%QX0.2` | `%QX0.3` |
| 3 | Added | `bEStop` | — | `BOOL`, `%IX0.4`, "Dừng khẩn (NC)" |
| 4 | Removed | `bLampRun` | `BOOL`, `%QX0.1`, "Đèn báo chạy" | — |
| 5 | Renamed | `bSensor` → `bSensorIn` | `%IX0.2`, `BOOL`, "Cảm biến sản phẩm" | same address, type and comment |
| 6 | Comment changed | `fbCounter` | "Internal" | "Bộ đếm sản phẩm" |

Notes:
- Change 5 has no stable ID to rely on: variables carry no ObjectId. A first version of the diff may
  report it as "removed `bSensor` + added `bSensorIn`". Rename detection can match on
  same address + same type + same comment.
- Change 6 is a side effect of CODESYS comment attribution (see `docs/xml-structure.md`).

## Body (ST)
- `bSensor` → `bSensorIn` in the counter call.
- `AND bEStop` added to the `bMotor` line.
- Line `bLampRun := bMotor;` removed.
- Whitespace only: `bMotor   :=` → `bMotor :=`. A good diff may flag this as whitespace-only.

## Must be ignored
- `contentHeader/@name` (`conveyor_v1.project` → `conveyor_v2.project`)
- `creationDateTime`, `modificationDateTime`
- Everything outside `PLC_PRG` (task, libraries, device, project structure): unchanged.
