# BALL x PIT Save Editor

Save file analysis and modification guide for [BALL x PIT](https://www.ballxpit.com/) by Devolver Digital.

> [!IMPORTANT]
> Pre-modified save files are available in [Releases](https://github.com/VdustR/game-save-ball-pit/releases). Copy the save files to your platform's save directory (see below).

> [!WARNING]
> This guide is provided for educational and personal use only. Use at your own risk. Modifying save files may cause crashes, data loss, or unexpected behavior. Always back up your original save before making changes.

## Game Version & Content

This guide and the release save files are based on **v1.299**, which includes:

| Content | Notes |
|---------|-------|
| Base Game (2025) | 8 levels, 17 characters, 70+ buildings |
| [The Regal Update](https://ballxpit.wiki.gg/wiki/Game_Updates) (2026-01-26) | +2 characters (The Carouser, The Falconer), +3 buildings (Party House, Falconry Hut, Adventurer's Guild), +8 balls, +3 passives, Endless Mode |

## Requirements

- Python 3
- Access to the save file directory (see below)

## Save File Location

The save format is cross-platform. The binary files (`meta1.yankai`, etc.) are identical across all platforms.

| Platform | Path |
|----------|------|
| Windows | `%USERPROFILE%\AppData\LocalLow\Kenny Sun\BALL x PIT\` |
| macOS | `~/Library/Application Support/Kenny Sun/BALL x PIT/` |
| Linux | `~/.config/unity3d/Kenny Sun/BALL x PIT/` |
| Android | `/sdcard/Android/data/com.devolverdigital.ballxpit/files/` |

> [!NOTE]
> iOS and console paths are not documented here. The binary format is the same — locate the save directory for your platform.

| File | Description |
|------|-------------|
| `meta1.yankai` | Main save file |
| `meta1_backup.yankai` | Backup save (should match `meta1.yankai`) |
| `saveslotinfo.balls` | Save slot metadata (level count, playtime, seed) |

> [!NOTE]
> On Android, `shared_prefs/CloudServicesLocalCopy.xml` and GMS snapshot files under `/data/data/com.google.android.gms/app_pgs_content_do_not_modify/` are cloud save caches — modifying them alone has no effect.

## Save File Format

The save files use .NET `BinaryFormatter` serialization with UTF-16LE encoded field names. Values can be located by searching for field name byte patterns in the binary data.

### Array Format

Int32 arrays are prefixed with `0x08` (primitive type), followed by a 4-byte element count. **Index 0 is a format marker (always `4`) and must not be modified.** Actual data starts at index 1.

```
08 [count:4B] [marker=4:4B] [value1:4B] [value2:4B] ...
```

For example, a `NumResources` array with count=4 contains 1 marker + 3 data values (Money, Rice, Wood).

### Stone Resource

The stone resource is stored as a standalone `int32` immediately **after** each of the `NumResources` and `TotalResources` arrays, not inside them.

## Modifiable Fields

### Resources

| Field | Type | Notes |
|-------|------|-------|
| `NumResources` | int32 array (count=4) | Index 0 = marker, 1 = Money, 2 = Rice, 3 = Wood |
| `TotalResources` | int32 array (count=4) | Same structure as above |
| Stone | standalone int32 | Located immediately after each resource array |

### Character Fields

| Field | Occurrences | Notes |
|-------|-------------|-------|
| `Lvl` | x56 | 0-indexed (value 99 = level 100). Match fields whose length prefix is `3` to avoid matching `ElevatorLvl`, `UpgradeLvl`, etc. |
| `CurXP` | x23 | Per character slot (the game has 23 internal slots, though only 19 characters are playable) |

### Buildings

| Field | Occurrences | Notes |
|-------|-------------|-------|
| `UpgradeLvl` | x78 | Finite buildings cap at levels 3 to 5. **Setting higher causes battle crashes.** |
| `UpgradePts` | x78 | Keep at 0 (= upgrade complete) |
| `CurState` | x78 | 0 = built, 2 = upgrading |

#### Building List (Max Level 5 Unless Noted)

<details>
<summary>Economy Buildings</summary>

**Resource Buildings** (can build multiples, no upgrade levels):
Wheat Field, Dense Wheat, Forest, Grand Tree, Boulder, Granite Slab

**Gathering Buildings** (can build multiples):
Farm, Lumberyard, Stone Mine, Gold Mine, Gatherer's Hut

**Other Economy**:
Watch Tower, Road Keeper, Market, Worker's Guild, Spa

</details>

<details>
<summary>Warfare Buildings</summary>

**Base Stat Bonus** (max 5):
Consulate (Leadership), Schoolhouse (Intelligence), Shoemaker (Speed), Gunsmith (Dexterity), Barracks (Strength), Clinic (Endurance)

**Stat Scaling** (max 5):
Wheelwright (Speed), Military Academy (Strength), Alchemist (Endurance), University (Intelligence), Archery Range (Dexterity), Diplomacy Hall (Leadership)

**Trophies** (max 5):
Boneyard, Snowy, Desert, Shroom, Gory, Smoldering, Heavenly, Void Trophy

**General** (max 5):
Abbey, Jeweler, Necromancer, Bank, Matchmaker, Magnet Factory, Candle Maker, Gambler's Den, Casino, Wishing Well, Evolution Chamber, Relic Collector, Meditation Tent, Exorcist, Gemsmith, Antique Shop, War Room, Bag Maker, Carpenter, Adventurer's Guild

</details>

<details>
<summary>Housing Buildings (max 5) — each unlocks a character</summary>

Sheriff's Office, Haunted House, Theater, Cozy Home, Villa, Mausoleum, Iron Fortress, Captain's Quarters, Campground, Single Family Home, Rocky Hill, Monastery, Laboratory, Veteran's Hut, Mansion, Falconry Hut, Party House

</details>

#### Infinitely Upgradeable Buildings

| Type | Building | Stat | Notes |
|------|----------|------|-------|
| 34 | Hospital | Endurance | +40 HP / level |
| 35 | Warrior's Guild | Strength | +1.5-2.5 base damage / level |
| 36 | Capitolium | Leadership | +0.75 baby ball count / level |
| 37 | Wagon Factory | Speed | +0.25 ball speed / level |
| 38 | Marksman's Guild | Dexterity | +0.02% crit / level |
| 39 | Grand Museum | Intelligence | +AOE/status/passive power / level |

Set `CurState` to `0` for these buildings to display as built. Very high values (9999+) may cause lag in battle.

### Playable Characters

There are 19 playable characters. Most are unlocked by building their corresponding housing building, which requires a blueprint drop from a specific level.

| # | Character | Unlock | Blueprint Source |
|---|-----------|--------|------------------|
| 1 | The Warrior | Default | — |
| 2 | The Itchy Finger | Sheriff's Office | The BONExYARD |
| 3 | The Repentant | Haunted House | The BONExYARD |
| 4 | The Cohabitants | Cozy Home | The BONExYARD |
| 5 | The Cogitator | Villa | The SNOWYxSHORES |
| 6 | The Embedded | Veteran's Hut | The SNOWYxSHORES |
| 7 | The Empty Nester | Single Family Home | The SNOWYxSHORES |
| 8 | The Shade | Mausoleum | The LIMINALxDESERT |
| 9 | The Makeshift Sisyphus | Rocky Hill | The LIMINALxDESERT |
| 10 | The Shieldbearer | Iron Fortress | The FUNGALxFOREST |
| 11 | The Spendthrift | Mansion | The FUNGALxFOREST |
| 12 | The Physicist | Laboratory | The FUNGALxFOREST |
| 13 | The Juggler | Theater | The GORYxGRASSLANDS |
| 14 | The Flagellant | Monastery | The GORYxGRASSLANDS |
| 15 | The Tactician | Captain's Quarters | The SMOLDERINGxDEPTHS |
| 16 | The Radical | Campground | The HEAVENLYxGATES |
| 17 | The Falconer | Falconry Hut | The HEAVENLYxGATES |
| 18 | The Carouser | Party House | The VASTxVOID |
| 19 | The False Messiah | Twitch Extension | PC-exclusive |

> [!NOTE]
> The Warrior is available by default, and The False Messiah requires the Twitch Extension (PC only). All other characters require building their housing building from a blueprint.

### Difficulty & Completion

| Field | Type | Notes |
|-------|------|-------|
| `BestDifficultyByChar` | int32 arrays | Value `N` = "fast +(N-2)". Max "fast +9" = value `11`. |
| `BestDifficultyByCharCombo` | int32 arrays | Same mapping |
| `BestTimeByChar` | int32 arrays | IEEE 754 float stored as int32 (e.g., 300.0s = `0x43960000`) |
| `DidComplete` | bool (1 byte) | Per level entry |
| `SawCompletionUnlocks` | bool (1 byte) | Per level entry |
| `SawElevatorReadyToUpgrade` | bool (1 byte) | Per level entry |
| `NumCompletedRuns` | int32 array [90] | Per-level completion count |
| `BestEndlessDepth` | int32 array [23] | Per character slot |

### Progression

| Field | Notes |
|-------|-------|
| `ElevatorLvl` | Controls level unlocks. Base game: 0–7 (8 levels). For NG+N, set to `(N + 1) * 8 - 1` (e.g., NG+1 = 15, NG+2 = 23, NG+3 = 31). |
| `WarRoomLevel` | Keep at original value (3) — higher values may cause battle UI issues |
| `BonusStats` | Keep at original values — higher values cause stat calculation overflow in battle |

### New Game+

Each NG+ tier adds 8 `LevelData` entries (~56 KB) to the save file. The game generates new entries automatically when you complete the current tier.

To unlock the next NG+ tier:

1. Set all `DidComplete` to `1`
2. Set all `BestDifficultyByChar` / `Combo` arrays to `11`
3. Set all `BestTimeByChar` / `Combo` arrays to a valid float (e.g., 300.0)
4. Set `SawCompletionUnlocks` and `SawElevatorReadyToUpgrade` to `1`
5. Set `ElevatorLvl` to `(N + 1) * 8 - 1` where N is the target NG+ tier
6. Launch the game to trigger generation of the next tier
7. Pull the updated save and repeat from step 1

## Fields That Must Not Be Modified

| Field | Reason |
|-------|--------|
| Array index 0 | Format marker (always `4`), not data |
| `ElevatorLvl` beyond correct range | Causes levels to become locked |
| `WarRoomLevel` (high values) | Battle UI issues |
| `BonusStats` (high values) | Stat calculation overflow in battle |
| Finite building `UpgradeLvl` (above cap) | Battle crashes |

## How to Apply

1. **Close the game** before modifying saves
2. Back up the original `meta1.yankai`
3. Edit with Python (see format above)
4. Copy the modified file to both `meta1.yankai` and `meta1_backup.yankai`
5. Launch the game

### Android (via ADB)

```bash
# Pull save
adb pull /sdcard/Android/data/com.devolverdigital.ballxpit/files/meta1.yankai save.yankai

# Edit with Python (see format above)

# Push save (ensure the game is not running)
adb shell am force-stop com.devolverdigital.ballxpit
adb push save.yankai /sdcard/Android/data/com.devolverdigital.ballxpit/files/meta1.yankai
adb push save.yankai /sdcard/Android/data/com.devolverdigital.ballxpit/files/meta1_backup.yankai
```

### PC / macOS / Linux

Copy the modified `meta1.yankai` and `meta1_backup.yankai` to the save directory for your platform (see [Save File Location](#save-file-location)).

## License

[MIT](LICENSE) &copy; 2026 VdustR
