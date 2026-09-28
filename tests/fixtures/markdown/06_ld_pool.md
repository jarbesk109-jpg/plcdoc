# 06\_ld\_pool\.project

- Product\: CODESYS V3\.5 SP22 Patch 3
- POUs\: FB\_PoolUser\, PLC\_PRG\, PRG\_Ladder
- Global variable lists\: GVL\_Pool

## I\/O table \(0\)

| Address | Direction | Name | Type | Scope | Comment |
|---------|-----------|------|------|-------|---------|

## Variables \(14\)

| Scope        | Section  | Name        | Type         | Address | Initial | Comment |
|--------------|----------|-------------|--------------|---------|---------|---------|
| GVL\_Pool    | global   | gPoolCount  | INT          |         |         |         |
| GVL\_Pool    | global   | gPoolFlag   | BOOL         |         |         |         |
| FB\_PoolUser | external | gPoolCount  | INT          |         |         |         |
| FB\_PoolUser | output   | xFlagSeen   | BOOL         |         |         |         |
| PLC\_PRG     | local    | fbPool      | FB\_PoolUser |         |         |         |
| PLC\_PRG     | local    | bHorn       | BOOL         |         |         |         |
| PLC\_PRG     | local    | bDoorClosed | BOOL         |         |         |         |
| PLC\_PRG     | local    | bLampRun    | BOOL         |         |         |         |
| PRG\_Ladder  | local    | xStart      | BOOL         |         |         |         |
| PRG\_Ladder  | local    | xDone       | BOOL         |         |         |         |
| PRG\_Ladder  | local    | xLamp       | BOOL         |         |         |         |
| PRG\_Ladder  | local    | iCount      | INT          |         |         |         |
| PRG\_Ladder  | local    | tonDelay    | TON          |         |         |         |
| PRG\_Ladder  | local    | tElapsed    | TIME         |         |         |         |
