# types\_qualifiers\.project

- Product\: CODESYS V3\.5 SP22 Patch 3
- POUs\: PLC\_PRG\, FB\_Motor\, FC\_Scale\, PRG\_Alarm
- Global variable lists\: GVL\_IO\, GVL\_Extra

## I\/O table \(20\)

| Address  | Direction | Name          | Type | Scope   | Comment                    |
|----------|-----------|---------------|------|---------|----------------------------|
| \%IX0\.0 | input     | bStart1       | BOOL | GVL\_IO | Start băng tải 1           |
| \%IX0\.1 | input     | bStop1        | BOOL | GVL\_IO | Stop băng tải 1 \(NC\)     |
| \%IX0\.2 | input     | bFault1       | BOOL | GVL\_IO | Quá tải băng tải 1         |
| \%IX0\.3 | input     | bStart2       | BOOL | GVL\_IO | Start băng tải 2           |
| \%IX0\.4 | input     | bStop2        | BOOL | GVL\_IO | Stop băng tải 2 \(NC\)     |
| \%IX0\.5 | input     | bFault2       | BOOL | GVL\_IO | Quá tải băng tải 2         |
| \%IX0\.6 | input     | bStart3       | BOOL | GVL\_IO | Start băng tải 3           |
| \%IX0\.7 | input     | bStop3        | BOOL | GVL\_IO | Stop băng tải 3 \(NC\)     |
| \%IX1\.0 | input     | bFault3       | BOOL | GVL\_IO | Quá tải băng tải 3         |
| \%IX1\.1 | input     | bEStopOK      | BOOL | GVL\_IO | Mạch dừng khẩn bình thường |
| \%IX1\.2 | input     | bDoorClosed   | BOOL | GVL\_IO | Cửa tủ đã đóng             |
| \%IW10   | input     | iTankLevelRaw | INT  | GVL\_IO | Mức bồn\, analog thô       |
| \%IW12   | input     | iTempRaw      | INT  | GVL\_IO | Nhiệt độ\, analog thô      |
| \%QX0\.0 | output    | bMotor1       | BOOL | GVL\_IO | Contactor băng tải 1       |
| \%QX0\.1 | output    | bMotor2       | BOOL | GVL\_IO | Contactor băng tải 2       |
| \%QX0\.2 | output    | bMotor3       | BOOL | GVL\_IO | Contactor băng tải 3       |
| \%QX0\.3 | output    | bLampAlarm    | BOOL | GVL\_IO | Đèn báo lỗi                |
| \%QX0\.4 | output    | bHorn         | BOOL | GVL\_IO | Còi báo                    |
| \%QW10   | output    | iSpeedRef     | INT  | GVL\_IO | Tốc độ đặt cho biến tần    |
| \%MX0\.0 | memory    | bAutoMode     | BOOL | GVL\_IO | Chế độ tự động             |

## Variables \(42\)

| Scope      | Section | Name          | Type                         | Address  | Initial   | Comment                          |
|------------|---------|---------------|------------------------------|----------|-----------|----------------------------------|
| GVL\_IO    | global  | bStart1       | BOOL                         | \%IX0\.0 |           | Start băng tải 1                 |
| GVL\_IO    | global  | bStop1        | BOOL                         | \%IX0\.1 |           | Stop băng tải 1 \(NC\)           |
| GVL\_IO    | global  | bFault1       | BOOL                         | \%IX0\.2 |           | Quá tải băng tải 1               |
| GVL\_IO    | global  | bStart2       | BOOL                         | \%IX0\.3 |           | Start băng tải 2                 |
| GVL\_IO    | global  | bStop2        | BOOL                         | \%IX0\.4 |           | Stop băng tải 2 \(NC\)           |
| GVL\_IO    | global  | bFault2       | BOOL                         | \%IX0\.5 |           | Quá tải băng tải 2               |
| GVL\_IO    | global  | bStart3       | BOOL                         | \%IX0\.6 |           | Start băng tải 3                 |
| GVL\_IO    | global  | bStop3        | BOOL                         | \%IX0\.7 |           | Stop băng tải 3 \(NC\)           |
| GVL\_IO    | global  | bFault3       | BOOL                         | \%IX1\.0 |           | Quá tải băng tải 3               |
| GVL\_IO    | global  | bEStopOK      | BOOL                         | \%IX1\.1 |           | Mạch dừng khẩn bình thường       |
| GVL\_IO    | global  | bDoorClosed   | BOOL                         | \%IX1\.2 |           | Cửa tủ đã đóng                   |
| GVL\_IO    | global  | iTankLevelRaw | INT                          | \%IW10   |           | Mức bồn\, analog thô             |
| GVL\_IO    | global  | iTempRaw      | INT                          | \%IW12   |           | Nhiệt độ\, analog thô            |
| GVL\_IO    | global  | bMotor1       | BOOL                         | \%QX0\.0 |           | Contactor băng tải 1             |
| GVL\_IO    | global  | bMotor2       | BOOL                         | \%QX0\.1 |           | Contactor băng tải 2             |
| GVL\_IO    | global  | bMotor3       | BOOL                         | \%QX0\.2 |           | Contactor băng tải 3             |
| GVL\_IO    | global  | bLampAlarm    | BOOL                         | \%QX0\.3 |           | Đèn báo lỗi                      |
| GVL\_IO    | global  | bHorn         | BOOL                         | \%QX0\.4 |           | Còi báo                          |
| GVL\_IO    | global  | iSpeedRef     | INT                          | \%QW10   |           | Tốc độ đặt cho biến tần          |
| GVL\_IO    | global  | bAutoMode     | BOOL                         | \%MX0\.0 |           | Chế độ tự động                   |
| GVL\_IO    | global  | rTankLevel    | REAL                         |          |           | Mức bồn \(\%\)                   |
| GVL\_IO    | global  | rTemp         | REAL                         |          |           | Nhiệt độ \(°C\)                  |
| GVL\_Extra | global  | aTemps        | ARRAY\[1\.\.4\] OF REAL      |          |           | Nhiệt độ 4 vùng                  |
| GVL\_Extra | global  | sRecipeName   | STRING\(20\)                 |          |           | Tên công thức                    |
| GVL\_Extra | global  | diTotalCount  | DINT                         |          |           | Tổng sản phẩm\, nhớ khi mất điện |
| GVL\_Extra | global  | MAX\_ZONES    | INT                          |          | 4         | Số vùng gia nhiệt                |
| PLC\_PRG   | local   | fbConv1       | FB\_Motor                    |          |           | Băng tải 1                       |
| PLC\_PRG   | local   | fbConv2       | FB\_Motor                    |          |           | Băng tải 2                       |
| PLC\_PRG   | local   | fbConv3       | FB\_Motor                    |          |           | Băng tải 3                       |
| PLC\_PRG   | local   | bLineReady    | BOOL                         |          |           | Dây chuyền sẵn sàng              |
| PLC\_PRG   | local   | aSetpoints    | ARRAY\[1\.\.3\] OF INT       |          | \(array\) | Điểm đặt                         |
| PLC\_PRG   | local   | aSpare        | ARRAY\[1\.\.2\] OF FB\_Motor |          |           | Băng tải dự phòng                |
| FB\_Motor  | input   | bStart        | BOOL                         |          |           | Lệnh chạy                        |
| FB\_Motor  | input   | bStop         | BOOL                         |          |           | Lệnh dừng \(NC\)                 |
| FB\_Motor  | input   | bFault        | BOOL                         |          |           | Tín hiệu lỗi                     |
| FB\_Motor  | input   | bInterlock    | BOOL                         |          |           | Điều kiện cho phép chạy          |
| FB\_Motor  | output  | bRun          | BOOL                         |          |           | Lệnh ra contactor                |
| FB\_Motor  | output  | bAlarm        | BOOL                         |          |           | Báo lỗi                          |
| FB\_Motor  | local   | tonFault      | TON                          |          |           | Lọc nhiễu tín hiệu lỗi           |
| FC\_Scale  | input   | iRaw          | INT                          |          |           | Giá trị analog thô               |
| FC\_Scale  | input   | rMin          | REAL                         |          |           | Giá trị kỹ thuật nhỏ nhất        |
| FC\_Scale  | input   | rMax          | REAL                         |          |           | Giá trị kỹ thuật lớn nhất        |
