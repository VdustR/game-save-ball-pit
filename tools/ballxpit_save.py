#!/usr/bin/env python3
"""Inspect, compare, and safely edit BALL x PIT BinaryFormatter saves."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


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


class SaveFormatError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def inspect_save(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    resources = {}
    for field in RESOURCE_FIELDS:
        _, values = find_resource_values(data, field)
        resources[field] = dict(zip(RESOURCE_NAMES, values, strict=True))
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
        current = dict(zip(RESOURCE_NAMES, values, strict=True))
        before[field] = current.copy()
        current.update(updates)
        if current["marker"] != 4:
            raise SaveFormatError(f"{field} marker changed unexpectedly")
        struct.pack_into(
            "<5i", edited, offset, *(current[name] for name in RESOURCE_NAMES)
        )
        after[field] = current

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(edited)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "inputSha256": sha256(original),
        "outputSha256": sha256(edited),
        "before": before,
        "after": after,
    }


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
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "inspect":
            result = inspect_save(args.save)
        elif args.command == "diff":
            result = diff_saves(args.old, args.new)
        else:
            updates = {
                name: getattr(args, name)
                for name in RESOURCE_NAMES[1:]
                if getattr(args, name) is not None
            }
            result = edit_resources(args.input, args.output, updates)
    except (OSError, SaveFormatError) as error:
        raise SystemExit(f"error: {error}") from error
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
