# BALL x PIT v1.301 Save Format Analysis

## Evidence

This analysis uses a save pulled over ADB from a physical Samsung Galaxy S23
running Android 16. The installed package was
`com.devolverdigital.ballxpit`, versionName `1.301`, versionCode `301`. The save
was last written on 2026-08-12 and was pulled on 2026-08-23.

The device and local SHA-256 hashes matched after transfer. The original files
were retained in a gitignored, read-only `backups/` directory. The repository
does not contain or publish the user's save.

The bundled `stats.csv` contains a run recorded with The Hoary Hoarder. This is
direct device evidence that the Naturalist Update content had run on the save.

## Comparison with v1.299

The v1.299 GitHub release asset is a historical baseline, not device evidence.

| Observation | v1.299 | v1.301 | Change |
|-------------|-------:|-------:|-------:|
| File size | 388,571 | 391,154 | +2,583 bytes |
| Exact `UpgradeLvl` matches | 78 | 83 | +5 |
| Exact `UpgradePts` matches | 78 | 83 | +5 |
| Length-prefixed `CurState` fields | 101 | 106 | +5 |
| Length-prefixed `Lvl` fields | 56 | 56 | unchanged |
| Length-prefixed `CurXP` fields | 23 | 23 | unchanged |
| Length-prefixed `BestEndlessDepth` fields | 32 | 32 | unchanged |

The additional five records containing `UpgradeLvl`, `UpgradePts`, and
`CurState` are an observed binary fact. Public update notes name Guildhall,
Ball House, and Unstable Tower after v1.299, but the remaining record-level
mapping has not been proven. The tool therefore reports field counts without
assigning unverified building names to individual records.

## Resource layout

The v1.301 save retains the resource structure documented for v1.299:

```text
08 04 00 00 00 04 00 00 00 [money:i32] [rice:i32] [wood:i32] [stone:i32]
```

The first `04 00 00 00` is the serialized array count. The second is the
protected marker at array index 0. Money, rice, and wood are the remaining
array elements. Stone is the standalone signed int32 immediately following the
array. The same layout appears once for each complete `NumResources` and
`TotalResources` value.

`NumResources` also occurs in reference/type data. An editor must locate a
complete nearby array header and require exactly one validated candidate. Raw
replacement of every UTF-16LE name match can corrupt the save.

## Main and backup files

The physical-device `meta1.yankai` and `meta1_backup.yankai` had the same size
and timestamp but different SHA-256 hashes. They differed at 25 byte positions.
Treat both as independent game-managed states: back up both and derive each
edited output from its corresponding original.

## Verification boundary

Verified on the physical Galaxy S23:

- package version and external save location;
- successful byte-for-byte ADB transfer;
- v1.301 field counts and resource decoding;
- resource edits while preserving size and all untouched bytes;
- ADB write-back of independently edited main and backup files;
- successful game launch and homestead load without a fatal or crash log;
- rice, wood, and stone displayed as `999,999` after writing `999999`;
- money displayed as `1,000,009` after writing `999999`, consistent with 10
  resources generated after the homestead loaded.

Not verified:

- iPhone/iOS container location or v1.14 iOS save compatibility;
- other Android versions, vendors, desktop platforms, or consoles;
- semantic identity and safe maximum level of each newly added building record.
