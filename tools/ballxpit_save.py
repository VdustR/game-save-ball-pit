#!/usr/bin/env python3
"""Inspect, compare, and safely edit BALL x PIT BinaryFormatter saves."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import struct
import tempfile
from pathlib import Path
from typing import Any


FIELDS = (
    "NumResources",
    "TotalResources",
    "Lvl",
    "CurXP",
    "UpgradeLvl",
    "UpgradePts",
    "CurState",
    "BestDifficultyByChar",
    "BestDifficultyByCharCombo",
    "BestTimeByChar",
    "BestTimeByCharCombo",
    "DidComplete",
    "SawCompletionUnlocks",
    "SawElevatorReadyToUpgrade",
    "NumCompletedRuns",
    "BestEndlessDepth",
    "ElevatorLvl",
    "WarRoomLevel",
    "BonusStats",
)

RESOURCE_FIELDS = ("NumResources", "TotalResources")
RESOURCE_NAMES = ("marker", "money", "rice", "wood", "stone")
ARRAY_HEADER = b"\x08\x04\x00\x00\x00"
MAX_INT32 = 2_147_483_647
INFINITE_BUILDING_TYPES = frozenset({34, 35, 36, 37, 38, 39})

# Stored, zero-based values observed in the project's v1.299 perfected save.
# Types absent from this table are preserved rather than assigned a guessed cap.
KNOWN_FINITE_BUILDING_CAPS = {
    0: 4, 1: 4, 2: 4, 3: 4, 4: 2, 5: 4, 6: 4, 9: 2, 11: 2, 13: 4,
    14: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 2, 21: 1, 22: 2, 23: 2,
    24: 0, 25: 0, 26: 2, 27: 2, 31: 2, 40: 2, 41: 0, 42: 0, 43: 0,
    44: 0, 45: 0, 47: 2, 48: 2, 57: 2, 58: 2, 60: 0, 61: 0, 62: 2,
    63: 2, 64: 1, 65: 2, 66: 2, 67: 2, 68: 0, 69: 0, 71: 0, 72: 2,
    73: 2, 74: 2, 75: 0, 77: 2, 78: 1, 79: 1, 80: 2, 81: 0, 82: 0,
    83: 3, 84: 0, 85: 0, 86: 0, 87: 4, 88: 0, 89: 0, 90: 0, 91: 0,
    92: 2, 93: 2, 94: 2, 95: 0, 99: 1, 100: 1, 102: 2, 104: 0,
}


class SaveFormatError(ValueError):
    pass


def encoded_field(name: str) -> bytes:
    return struct.pack("<I", len(name)) + name.encode("utf-16le")


def unique_field_offset(data: bytes, name: str) -> int:
    field = encoded_field(name)
    offsets = []
    start = 0
    while (offset := data.find(field, start)) >= 0:
        offsets.append(offset)
        start = offset + len(field)
    if len(offsets) != 1:
        raise SaveFormatError(f"expected one {name!r} field, found {len(offsets)}")
    return offsets[0]


def field_value_offsets(data: bytes, name: str, start: int, end: int) -> list[int]:
    field = encoded_field(name)
    offsets = []
    cursor = start
    while (field_offset := data.find(field, cursor, end)) >= 0:
        value_offset = field_offset + len(field)
        if value_offset + 4 > end:
            raise SaveFormatError(f"truncated {name} value at 0x{value_offset:x}")
        offsets.append(value_offset)
        cursor = value_offset + 4
    return offsets


def int_array_offsets(
    data: bytes, name: str, start: int, end: int
) -> list[tuple[int, int]]:
    field = encoded_field(name)
    arrays = []
    cursor = start
    while (field_offset := data.find(field, cursor, end)) >= 0:
        search_start = field_offset + len(field)
        candidates = []
        for header_offset in range(search_start, min(search_start + 64, end - 9)):
            if data[header_offset] != 8:
                continue
            count = struct.unpack_from("<i", data, header_offset + 1)[0]
            marker = struct.unpack_from("<i", data, header_offset + 5)[0]
            values_offset = header_offset + 9
            if 1 <= count <= 1000 and marker == 4 and values_offset + count * 4 <= end:
                candidates.append((values_offset, count))
        if len(candidates) != 1:
            raise SaveFormatError(
                f"expected one {name} array near 0x{field_offset:x}, "
                f"found {len(candidates)}"
            )
        arrays.append(candidates[0])
        cursor = candidates[0][0] + candidates[0][1] * 4
    return arrays


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_new_file(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(mode)
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise SaveFormatError("output already exists; refusing to overwrite it") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def count_fields(data: bytes) -> dict[str, int]:
    return {
        field: data.count(struct.pack("<I", len(field)) + field.encode("utf-16le"))
        for field in FIELDS
    }


def find_resource_values(data: bytes, field: str) -> tuple[int, tuple[int, ...]]:
    if field not in RESOURCE_FIELDS:
        raise SaveFormatError(f"unsupported resource field: {field}")

    encoded = struct.pack("<I", len(field)) + field.encode("utf-16le")
    candidates: list[int] = []
    start = 0
    while (field_offset := data.find(encoded, start)) >= 0:
        header_offset = data.find(ARRAY_HEADER, field_offset, field_offset + 192)
        if header_offset >= 0:
            value_offset = header_offset + len(ARRAY_HEADER)
            if value_offset + 20 <= len(data):
                values = struct.unpack_from("<5i", data, value_offset)
                if values[0] == 4:
                    candidates.append(value_offset)
        start = field_offset + len(encoded)

    if len(candidates) != 1:
        raise SaveFormatError(
            f"expected one validated {field} array, found {len(candidates)}"
        )
    offset = candidates[0]
    return offset, struct.unpack_from("<5i", data, offset)


def inspect_save(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    resources = {}
    for field in RESOURCE_FIELDS:
        _, values = find_resource_values(data, field)
        resources[field] = {
            name: values[index] for index, name in enumerate(RESOURCE_NAMES)
        }
    return {
        "path": str(path),
        "size": len(data),
        "sha256": sha256(data),
        "fieldCounts": count_fields(data),
        "resources": resources,
    }


def diff_saves(old_path: Path, new_path: Path) -> dict[str, object]:
    old = inspect_save(old_path)
    new = inspect_save(new_path)
    fields = {
        field: {"old": old["fieldCounts"][field], "new": new["fieldCounts"][field]}
        for field in FIELDS
        if old["fieldCounts"][field] != new["fieldCounts"][field]
    }
    return {
        "old": {"path": old["path"], "size": old["size"], "sha256": old["sha256"]},
        "new": {"path": new["path"], "size": new["size"], "sha256": new["sha256"]},
        "sizeDelta": new["size"] - old["size"],
        "fieldCountChanges": fields,
        "resourceChanges": {
            field: {
                name: {"old": old["resources"][field][name], "new": new["resources"][field][name]}
                for name in RESOURCE_NAMES
                if old["resources"][field][name] != new["resources"][field][name]
            }
            for field in RESOURCE_FIELDS
        },
    }


def edit_resources(
    input_path: Path, output_path: Path, updates: dict[str, int]
) -> dict[str, object]:
    if input_path.resolve() == output_path.resolve():
        raise SaveFormatError("output must differ from input; in-place editing is refused")
    if output_path.exists():
        raise SaveFormatError("output already exists; refusing to overwrite it")
    if not updates:
        raise SaveFormatError("at least one resource value is required")
    for name, value in updates.items():
        if name == "marker" or name not in RESOURCE_NAMES:
            raise SaveFormatError(f"unsupported resource: {name}")
        if not 0 <= value <= 2_147_483_647:
            raise SaveFormatError(f"{name} is outside the signed int32 safe range")

    original = input_path.read_bytes()
    edited = bytearray(original)
    before = {}
    after = {}
    for field in RESOURCE_FIELDS:
        offset, values = find_resource_values(original, field)
        current: dict[str, int] = {
            name: values[index] for index, name in enumerate(RESOURCE_NAMES)
        }
        before[field] = current.copy()
        current.update(updates)
        if current["marker"] != 4:
            raise SaveFormatError(f"{field} marker changed unexpectedly")
        struct.pack_into(
            "<5i", edited, offset, *(current[name] for name in RESOURCE_NAMES)
        )
        after[field] = current

    write_new_file(
        output_path, bytes(edited), stat.S_IMODE(input_path.stat().st_mode)
    )
    return {
        "input": str(input_path),
        "output": str(output_path),
        "inputSha256": sha256(original),
        "outputSha256": sha256(bytes(edited)),
        "before": before,
        "after": after,
    }


def edit_meta(
    input_path: Path,
    output_path: Path,
    resource_value: int | None = None,
    infinite_building_level: int | None = None,
    max_known_finite_buildings: bool = False,
    character_level: int | None = None,
    character_types: frozenset[int] | None = None,
    unlock_wiki: bool = False,
) -> dict[str, object]:
    if input_path.resolve() == output_path.resolve():
        raise SaveFormatError("output must differ from input; in-place editing is refused")
    if output_path.exists():
        raise SaveFormatError("output already exists; refusing to overwrite it")
    if not any(
        (
            resource_value is not None,
            infinite_building_level is not None,
            max_known_finite_buildings,
            character_level is not None,
            unlock_wiki,
        )
    ):
        raise SaveFormatError("at least one edit option is required")
    if resource_value is not None and not 0 <= resource_value <= MAX_INT32:
        raise SaveFormatError("resource value is outside the signed int32 range")
    if infinite_building_level is not None and not 0 <= infinite_building_level <= MAX_INT32:
        raise SaveFormatError("building level is outside the signed int32 range")
    if character_level is not None and not 1 <= character_level <= 100:
        raise SaveFormatError("character level must be between 1 and 100")
    if character_types is not None and character_level is None:
        raise SaveFormatError("--character-types requires --character-level")

    original = input_path.read_bytes()
    edited = bytearray(original)
    result: dict[str, object] = {
        "input": str(input_path),
        "output": str(output_path),
        "inputSha256": sha256(original),
    }

    if resource_value is not None:
        offset, values = find_resource_values(original, "NumResources")
        struct.pack_into("<5i", edited, offset, values[0], *([resource_value] * 4))
        result["currentResourcesBefore"] = {
            name: values[index] for index, name in enumerate(RESOURCE_NAMES)
        }
        result["currentResourcesAfter"] = {
            name: resource_value for name in RESOURCE_NAMES[1:]
        }

    if infinite_building_level is not None or max_known_finite_buildings:
        buildings_start = unique_field_offset(original, "Buildings")
        buildings_end = unique_field_offset(original, "Chars")
        type_offsets = field_value_offsets(original, "Type", buildings_start, buildings_end)
        level_offsets = field_value_offsets(
            original, "UpgradeLvl", buildings_start, buildings_end
        )
        point_offsets = field_value_offsets(
            original, "UpgradePts", buildings_start, buildings_end
        )
        state_offsets = field_value_offsets(
            original, "CurState", buildings_start, buildings_end
        )
        if not level_offsets or not (
            len(type_offsets)
            == len(level_offsets)
            == len(point_offsets)
            == len(state_offsets)
        ):
            raise SaveFormatError(
                "Buildings section has mismatched Type, UpgradeLvl, UpgradePts, "
                "and CurState fields"
            )

        infinite_counts: dict[str, int] = {}
        finite_counts: dict[str, int] = {}
        unknown_types: set[int] = set()
        for index, type_offset in enumerate(type_offsets):
            record_end = (
                type_offsets[index + 1]
                if index + 1 < len(type_offsets)
                else buildings_end
            )
            record_levels = [
                offset for offset in level_offsets if type_offset < offset < record_end
            ]
            record_points = [
                offset for offset in point_offsets if type_offset < offset < record_end
            ]
            record_states = [
                offset for offset in state_offsets if type_offset < offset < record_end
            ]
            if not (
                len(record_levels) == len(record_points) == len(record_states) == 1
            ):
                raise SaveFormatError("invalid BuildingInst field containment")
            level_offset = record_levels[0]
            point_offset = record_points[0]
            state_offset = record_states[0]
            building_type = struct.unpack_from("<i", original, type_offset)[0]
            if (
                infinite_building_level is not None
                and building_type in INFINITE_BUILDING_TYPES
            ):
                struct.pack_into("<i", edited, level_offset, infinite_building_level)
                struct.pack_into("<i", edited, point_offset, 0)
                struct.pack_into("<i", edited, state_offset, 0)
                key = str(building_type)
                infinite_counts[key] = infinite_counts.get(key, 0) + 1
            elif max_known_finite_buildings:
                if building_type in KNOWN_FINITE_BUILDING_CAPS:
                    struct.pack_into(
                        "<i", edited, level_offset, KNOWN_FINITE_BUILDING_CAPS[building_type]
                    )
                    struct.pack_into("<i", edited, point_offset, 0)
                    struct.pack_into("<i", edited, state_offset, 0)
                    key = str(building_type)
                    finite_counts[key] = finite_counts.get(key, 0) + 1
                elif building_type not in INFINITE_BUILDING_TYPES:
                    unknown_types.add(building_type)
        result["infiniteBuildingTypesEdited"] = infinite_counts
        result["knownFiniteBuildingTypesMaxed"] = finite_counts
        result["unknownFiniteBuildingTypesPreserved"] = sorted(unknown_types)

    if character_level is not None:
        chars_start = unique_field_offset(original, "Chars")
        chars_end = unique_field_offset(original, "Blueprints")
        all_type_offsets = field_value_offsets(original, "Type", chars_start, chars_end)
        state_offsets = field_value_offsets(original, "CurState", chars_start, chars_end)
        all_level_offsets = field_value_offsets(original, "Lvl", chars_start, chars_end)
        xp_offsets = field_value_offsets(original, "CurXP", chars_start, chars_end)

        char_type_offsets = []
        previous_state = chars_start
        for state_offset in state_offsets:
            candidates = [
                offset
                for offset in all_type_offsets
                if previous_state < offset < state_offset
            ]
            if not candidates:
                raise SaveFormatError("character record is missing its top-level Type")
            char_type_offsets.append(candidates[-1])
            previous_state = state_offset

        char_level_offsets = []
        char_xp_offsets = []
        for index, type_offset in enumerate(char_type_offsets):
            record_end = (
                char_type_offsets[index + 1]
                if index + 1 < len(char_type_offsets)
                else chars_end
            )
            record_xp = [
                offset for offset in xp_offsets if type_offset < offset < record_end
            ]
            if len(record_xp) != 1:
                raise SaveFormatError("character record has invalid CurXP containment")
            xp_offset = record_xp[0]
            record_levels = [
                offset
                for offset in all_level_offsets
                if type_offset < offset < xp_offset
            ]
            xp_field_offset = xp_offset - len(encoded_field("CurXP"))
            adjacent_levels = [
                offset
                for offset in record_levels
                if 0 <= xp_field_offset - (offset + 4) <= 8
            ]
            if len(adjacent_levels) != 1:
                raise SaveFormatError(
                    "character record has invalid top-level Lvl adjacency"
                )
            char_level_offsets.append(adjacent_levels[0])
            char_xp_offsets.append(xp_offset)
        if not char_type_offsets or not (
            len(char_type_offsets) == len(char_level_offsets) == len(char_xp_offsets)
        ):
            raise SaveFormatError("Chars section has mismatched character fields")

        stored_level = character_level - 1
        found_types: set[int] = set()
        edited_characters: dict[str, dict[str, int]] = {}
        for index, type_offset in enumerate(char_type_offsets):
            character_type = struct.unpack_from("<i", original, type_offset)[0]
            if character_types is not None and character_type not in character_types:
                continue
            found_types.add(character_type)
            level_offset = char_level_offsets[index]
            xp_offset = char_xp_offsets[index]
            edited_characters[str(character_type)] = {
                "storedLevelBefore": struct.unpack_from("<i", original, level_offset)[0],
                "xpBefore": struct.unpack_from("<i", original, xp_offset)[0],
            }
            struct.pack_into("<i", edited, level_offset, stored_level)
            struct.pack_into("<i", edited, xp_offset, 0)
        if character_types is not None:
            missing_types = sorted(character_types - found_types)
            if missing_types:
                raise SaveFormatError(f"character types not present: {missing_types}")
        result["characterEdit"] = {
            "displayLevelAfter": character_level,
            "storedLevelAfter": stored_level,
            "xpAfter": 0,
            "charactersEdited": edited_characters,
        }

    if unlock_wiki:
        hero_start = unique_field_offset(original, "HeroStats")
        passive_start = unique_field_offset(original, "PassiveStats")
        wiki_end = unique_field_offset(original, "NumHarvests")
        if not hero_start < passive_start < wiki_end:
            raise SaveFormatError("invalid wiki statistics section boundaries")
        hero_obtained = field_value_offsets(
            original, "NumObtained", hero_start, passive_start
        )
        passive_obtained = field_value_offsets(
            original, "NumObtained", passive_start, wiki_end
        )
        combo_arrays = int_array_offsets(original, "NumCombos", hero_start, passive_start)
        if (
            not hero_obtained
            or not passive_obtained
            or len(combo_arrays) != len(hero_obtained)
            or any(count != len(hero_obtained) for _, count in combo_arrays)
        ):
            raise SaveFormatError("unexpected HeroStats or PassiveStats structure")
        obtained_changed = 0
        combo_cells_changed = 0
        for offset in hero_obtained + passive_obtained:
            if struct.unpack_from("<i", original, offset)[0] <= 0:
                struct.pack_into("<i", edited, offset, 1)
                obtained_changed += 1
        for values_offset, count in combo_arrays:
            for index in range(count):
                offset = values_offset + index * 4
                if struct.unpack_from("<i", original, offset)[0] <= 0:
                    struct.pack_into("<i", edited, offset, 1)
                    combo_cells_changed += 1
        result["wikiUnlock"] = {
            "heroEntries": len(hero_obtained),
            "passiveEntries": len(passive_obtained),
            "comboRows": len(combo_arrays),
            "obtainedCountersChanged": obtained_changed,
            "comboCellsChanged": combo_cells_changed,
        }

    write_new_file(
        output_path, bytes(edited), stat.S_IMODE(input_path.stat().st_mode)
    )
    written = output_path.read_bytes()
    if len(written) != len(original) or written != bytes(edited):
        output_path.unlink(missing_ok=True)
        raise SaveFormatError("written output failed byte-for-byte verification")
    result["outputSha256"] = sha256(written)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="inspect one save")
    inspect_parser.add_argument("save", type=Path)
    diff_parser = subparsers.add_parser("diff", help="compare two saves")
    diff_parser.add_argument("old", type=Path)
    diff_parser.add_argument("new", type=Path)
    edit_parser = subparsers.add_parser("edit-resources", help="write an edited copy")
    edit_parser.add_argument("input", type=Path)
    edit_parser.add_argument("output", type=Path)
    for name in RESOURCE_NAMES[1:]:
        edit_parser.add_argument(f"--{name}", type=int)
    meta_parser = subparsers.add_parser("edit-meta", help="edit progression metadata")
    meta_parser.add_argument("input", type=Path)
    meta_parser.add_argument("output", type=Path)
    meta_parser.add_argument(
        "--resources", type=int, help="set all four current resources"
    )
    meta_parser.add_argument(
        "--infinite-building-level",
        type=int,
        help="set building types 34-39 to this stored level",
    )
    meta_parser.add_argument(
        "--max-known-finite-buildings",
        action="store_true",
        help="apply known finite caps and preserve unknown types",
    )
    meta_parser.add_argument(
        "--character-level",
        type=int,
        help="set displayed character level from 1 to 100 and reset XP",
    )
    meta_parser.add_argument(
        "--character-types",
        help="comma-separated character type IDs (default: all)",
    )
    meta_parser.add_argument(
        "--unlock-wiki",
        action="store_true",
        help="discover ball, passive, and combination entries",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "inspect":
            result = inspect_save(args.save)
        elif args.command == "diff":
            result = diff_saves(args.old, args.new)
        elif args.command == "edit-resources":
            updates = {
                name: getattr(args, name)
                for name in RESOURCE_NAMES[1:]
                if getattr(args, name) is not None
            }
            result = edit_resources(args.input, args.output, updates)
        else:
            character_types = None
            if args.character_types is not None:
                character_types = frozenset(
                    int(value.strip())
                    for value in args.character_types.split(",")
                    if value.strip()
                )
                if not character_types:
                    raise SaveFormatError("--character-types cannot be empty")
            result = edit_meta(
                args.input,
                args.output,
                resource_value=args.resources,
                infinite_building_level=args.infinite_building_level,
                max_known_finite_buildings=args.max_known_finite_buildings,
                character_level=args.character_level,
                character_types=character_types,
                unlock_wiki=args.unlock_wiki,
            )
    except (OSError, SaveFormatError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
