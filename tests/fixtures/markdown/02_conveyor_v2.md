# conveyor\_v2\.project

- Product\: CODESYS V3\.5 SP22 Patch 3
- POUs\: PLC\_PRG
- Global variable lists\: none

## I\/O table \(7\)

| Address  | Direction | Name      | Type | Scope    | Comment             |
|----------|-----------|-----------|------|----------|---------------------|
| \%IX0\.0 | input     | bStart    | BOOL | PLC\_PRG | Nút Start \(NO\)    |
| \%IX0\.1 | input     | bStop     | BOOL | PLC\_PRG | Nút Stop \(NC\)     |
| \%IX0\.2 | input     | bSensorIn | BOOL | PLC\_PRG | Cảm biến sản phẩm   |
| \%IX0\.3 | input     | bReset    | BOOL | PLC\_PRG | Nút reset bộ đếm    |
| \%IX0\.4 | input     | bEStop    | BOOL | PLC\_PRG | Dừng khẩn \(NC\)    |
| \%QX0\.0 | output    | bMotor    | BOOL | PLC\_PRG | Contactor băng tải  |
| \%QX0\.3 | output    | bLampDone | BOOL | PLC\_PRG | Đèn báo đủ số lượng |

## Variables \(10\)

| Scope    | Section | Name      | Type | Address  | Initial | Comment             |
|----------|---------|-----------|------|----------|---------|---------------------|
| PLC\_PRG | local   | bStart    | BOOL | \%IX0\.0 |         | Nút Start \(NO\)    |
| PLC\_PRG | local   | bStop     | BOOL | \%IX0\.1 |         | Nút Stop \(NC\)     |
| PLC\_PRG | local   | bSensorIn | BOOL | \%IX0\.2 |         | Cảm biến sản phẩm   |
| PLC\_PRG | local   | bReset    | BOOL | \%IX0\.3 |         | Nút reset bộ đếm    |
| PLC\_PRG | local   | bEStop    | BOOL | \%IX0\.4 |         | Dừng khẩn \(NC\)    |
| PLC\_PRG | local   | bMotor    | BOOL | \%QX0\.0 |         | Contactor băng tải  |
| PLC\_PRG | local   | bLampDone | BOOL | \%QX0\.3 |         | Đèn báo đủ số lượng |
| PLC\_PRG | local   | fbCounter | CTU  |          |         | Bộ đếm sản phẩm     |
| PLC\_PRG | local   | iCount    | INT  |          |         |                     |
| PLC\_PRG | local   | iPreset   | INT  |          | 20      |                     |
