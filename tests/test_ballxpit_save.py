import struct
import tempfile
import unittest
from pathlib import Path

from tools.ballxpit_save import (
    SaveFormatError,
    count_fields,
    edit_meta,
    edit_resources,
    encoded_field,
    field_value_offsets,
    find_resource_values,
    int_array_offsets,
    parse_character_types,
    unique_field_offset,
    validate_save_envelope,
)


def fixture(
    resources=(4, 10, 20, 30, 40),
    totals=(4, 100, 200, 300, 400),
    complete=True,
):
    def field(name, values):
        return struct.pack("<I", len(name)) + name.encode("utf-16le") + b"type-metadata" + b"\x08\x04\x00\x00\x00" + struct.pack("<5i", *values)

    data = (
        b"\x02"
        + encoded_field("MetaSaveData, Assembly-CSharp")
        + field("NumResources", resources)
        + field("TotalResources", totals)
    )
    if complete:
        for name in (
            "Buildings",
            "Chars",
            "Blueprints",
            "HeroStats",
            "PassiveStats",
            "NumHarvests",
        ):
            data += encoded_field(name)
        data += named_int("NumBossBlueprintsDropped", 0) + b"\x05"
    return data


def named_int(name, value):
    return encoded_field(name) + struct.pack("<i", value)


def named_int_array(name, values):
    return (
        encoded_field(name)
        + b"array-metadata"
        + b"\x08"
        + struct.pack("<i", len(values))
        + struct.pack("<i", 4)
        + struct.pack(f"<{len(values)}i", *values)
    )


def meta_fixture():
    buildings = encoded_field("Buildings")
    buildings += named_int("Type", 34) + named_int("UpgradePts", 10)
    buildings += named_int("UpgradeLvl", 5) + named_int("CurState", 2)
    buildings += named_int("Type", 0) + named_int("UpgradePts", 20)
    buildings += named_int("UpgradeLvl", 0) + named_int("CurState", 2)
    buildings += named_int("Type", 999) + named_int("UpgradePts", 30)
    buildings += named_int("UpgradeLvl", 7) + named_int("CurState", 2)

    chars = encoded_field("Chars")
    chars += named_int("Type", 0) + named_int("CurState", 0)
    chars += named_int("Type", 70) + named_int("Lvl", 2) + named_int("CurXP", 123)
    chars += named_int("Type", 5) + named_int("CurState", 0)
    chars += named_int("Type", 71) + named_int("Lvl", 8) + named_int("CurXP", 456)
    chars += encoded_field("Blueprints")

    wiki = encoded_field("HeroStats")
    wiki += named_int("NumObtained", 0) + named_int_array("NumCombos", [0, 2])
    wiki += named_int("NumObtained", 3) + named_int_array("NumCombos", [0, 0])
    wiki += encoded_field("PassiveStats")
    wiki += named_int("NumObtained", 0) + named_int("NumObtained", 4)
    wiki += encoded_field("NumHarvests")
    return (
        fixture(complete=False)
        + buildings
        + chars
        + wiki
        + named_int("NumBossBlueprintsDropped", 0)
        + b"\x05"
    )


class SaveToolTests(unittest.TestCase):
    def test_reads_resource_arrays_and_standalone_stone(self):
        data = fixture()
        self.assertEqual(find_resource_values(data, "NumResources")[1], (4, 10, 20, 30, 40))
        self.assertEqual(find_resource_values(data, "TotalResources")[1], (4, 100, 200, 300, 400))

    def test_field_counts_require_length_prefixed_complete_names(self):
        data = struct.pack("<I", 3) + "Lvl".encode("utf-16le")
        data += struct.pack("<I", 10) + "UpgradeLvl".encode("utf-16le")
        self.assertEqual(count_fields(data)["Lvl"], 1)
        self.assertEqual(count_fields(data)["UpgradeLvl"], 1)

    def test_edits_both_current_and_total_resources_without_touching_input(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            original = fixture()
            input_path.write_bytes(original)
            result = edit_resources(input_path, output_path, {"money": 999, "stone": 888})
            self.assertEqual(input_path.read_bytes(), original)
            self.assertNotEqual(result["inputSha256"], result["outputSha256"])
            for field in ("NumResources", "TotalResources"):
                values = find_resource_values(output_path.read_bytes(), field)[1]
                self.assertEqual(values[0], 4)
                self.assertEqual(values[1], 999)
                self.assertEqual(values[4], 888)

    def test_refuses_in_place_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.yankai"
            path.write_bytes(fixture())
            with self.assertRaisesRegex(SaveFormatError, "in-place"):
                edit_resources(path, path, {"money": 1})

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            input_path.write_bytes(fixture())
            output_path.write_bytes(b"keep me")
            with self.assertRaisesRegex(SaveFormatError, "already exists"):
                edit_resources(input_path, output_path, {"money": 1})
            self.assertEqual(output_path.read_bytes(), b"keep me")

    def test_rejects_ambiguous_arrays(self):
        duplicate = fixture() + fixture()
        with self.assertRaisesRegex(SaveFormatError, "found 2"):
            find_resource_values(duplicate, "NumResources")

    def test_rejects_invalid_marker(self):
        with self.assertRaisesRegex(SaveFormatError, "found 0"):
            find_resource_values(fixture(resources=(3, 1, 2, 3, 4)), "NumResources")

    def test_edit_meta_targets_structural_records_and_preserves_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            input_path.write_bytes(meta_fixture())
            result = edit_meta(
                input_path,
                output_path,
                resource_value=10_000,
                infinite_building_level=20,
                max_known_finite_buildings=True,
                character_level=50,
                character_types=frozenset({5}),
                unlock_wiki=True,
            )
            edited = output_path.read_bytes()

            self.assertEqual(
                find_resource_values(edited, "NumResources")[1],
                (4, 10_000, 10_000, 10_000, 10_000),
            )
            self.assertEqual(
                find_resource_values(edited, "TotalResources")[1],
                (4, 100, 200, 300, 400),
            )

            buildings_start = unique_field_offset(edited, "Buildings")
            buildings_end = unique_field_offset(edited, "Chars")
            building_levels = field_value_offsets(
                edited, "UpgradeLvl", buildings_start, buildings_end
            )
            building_points = field_value_offsets(
                edited, "UpgradePts", buildings_start, buildings_end
            )
            building_states = field_value_offsets(
                edited, "CurState", buildings_start, buildings_end
            )
            self.assertEqual(
                [struct.unpack_from("<i", edited, offset)[0] for offset in building_levels],
                [20, 4, 7],
            )
            self.assertEqual(
                [struct.unpack_from("<i", edited, offset)[0] for offset in building_points],
                [0, 0, 30],
            )
            self.assertEqual(
                [struct.unpack_from("<i", edited, offset)[0] for offset in building_states],
                [0, 0, 2],
            )
            self.assertEqual(result["unknownFiniteBuildingTypesPreserved"], [999])
            self.assertEqual(
                result["currentResourcesBefore"],
                {"money": 10, "rice": 20, "wood": 30, "stone": 40},
            )
            self.assertEqual(
                set(result["currentResourcesBefore"]),
                set(result["currentResourcesAfter"]),
            )

            chars_start = unique_field_offset(edited, "Chars")
            chars_end = unique_field_offset(edited, "Blueprints")
            char_levels = field_value_offsets(edited, "Lvl", chars_start, chars_end)
            char_xp = field_value_offsets(edited, "CurXP", chars_start, chars_end)
            self.assertEqual(
                [struct.unpack_from("<i", edited, offset)[0] for offset in char_levels],
                [2, 49],
            )
            self.assertEqual(
                [struct.unpack_from("<i", edited, offset)[0] for offset in char_xp],
                [123, 0],
            )

            hero_start = unique_field_offset(edited, "HeroStats")
            passive_start = unique_field_offset(edited, "PassiveStats")
            combo_arrays = int_array_offsets(edited, "NumCombos", hero_start, passive_start)
            for values_offset, count in combo_arrays:
                self.assertTrue(
                    all(
                        value >= 1
                        for value in struct.unpack_from(
                            f"<{count}i", edited, values_offset
                        )
                    )
                )

    def test_edit_meta_requires_an_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            input_path.write_bytes(meta_fixture())
            with self.assertRaisesRegex(SaveFormatError, "at least one edit"):
                edit_meta(input_path, output_path)

    def test_edit_meta_rejects_character_level_above_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            input_path.write_bytes(meta_fixture())
            with self.assertRaisesRegex(SaveFormatError, "between 1 and 100"):
                edit_meta(input_path, output_path, character_level=101)

    def test_edit_meta_rejects_interleaved_building_records(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            malformed = fixture(complete=False) + encoded_field("Buildings")
            malformed += named_int("Type", 34) + named_int("Type", 0)
            malformed += named_int("UpgradePts", 0) + named_int("UpgradeLvl", 0)
            malformed += named_int("CurState", 0)
            malformed += named_int("UpgradePts", 0) + named_int("UpgradeLvl", 0)
            malformed += named_int("CurState", 0)
            malformed += encoded_field("Chars")
            malformed += encoded_field("Blueprints")
            malformed += encoded_field("HeroStats")
            malformed += encoded_field("PassiveStats")
            malformed += encoded_field("NumHarvests")
            malformed += named_int("NumBossBlueprintsDropped", 0) + b"\x05"
            input_path.write_bytes(malformed)
            with self.assertRaisesRegex(SaveFormatError, "field containment"):
                edit_meta(input_path, output_path, infinite_building_level=20)

    def test_edit_meta_does_not_follow_broken_output_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            target_path = Path(directory) / "missing-target.yankai"
            input_path.write_bytes(meta_fixture())
            output_path.symlink_to(target_path)
            with self.assertRaisesRegex(SaveFormatError, "already exists"):
                edit_meta(input_path, output_path, resource_value=10_000)
            self.assertFalse(target_path.exists())

    def test_edit_meta_rejects_nonadjacent_character_level(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            malformed = fixture(complete=False) + encoded_field("Buildings")
            malformed += encoded_field("Chars")
            malformed += named_int("Type", 0) + named_int("CurState", 0)
            malformed += named_int("Lvl", 2) + named_int("Unexpected", 9)
            malformed += named_int("CurXP", 123) + encoded_field("Blueprints")
            malformed += encoded_field("HeroStats")
            malformed += encoded_field("PassiveStats")
            malformed += encoded_field("NumHarvests")
            malformed += named_int("NumBossBlueprintsDropped", 0) + b"\x05"
            input_path.write_bytes(malformed)
            with self.assertRaisesRegex(SaveFormatError, "Lvl adjacency"):
                edit_meta(input_path, output_path, character_level=50)

    def test_edit_meta_rejects_truncated_save_before_publishing(self):
        original = meta_fixture()
        cut_offsets = [
            unique_field_offset(original, name)
            for name in (
                "Buildings",
                "Chars",
                "Blueprints",
                "HeroStats",
                "PassiveStats",
                "NumHarvests",
            )
        ]
        cut_offsets.append(len(original) - 1)
        with tempfile.TemporaryDirectory() as directory:
            for index, cut_offset in enumerate(cut_offsets):
                with self.subTest(cut_offset=cut_offset):
                    input_path = Path(directory) / f"input-{index}.yankai"
                    output_path = Path(directory) / f"output-{index}.yankai"
                    input_path.write_bytes(original[:cut_offset])
                    with self.assertRaises(SaveFormatError):
                        edit_meta(input_path, output_path, resource_value=123)
                    self.assertFalse(output_path.exists())

    def test_edit_meta_rejects_leading_truncation_before_publishing(self):
        original = meta_fixture()
        with tempfile.TemporaryDirectory() as directory:
            for index, cut_offset in enumerate((1, 2, 8, 32)):
                with self.subTest(cut_offset=cut_offset):
                    input_path = Path(directory) / f"input-{index}.yankai"
                    output_path = Path(directory) / f"output-{index}.yankai"
                    input_path.write_bytes(original[cut_offset:])
                    with self.assertRaises(SaveFormatError):
                        edit_meta(input_path, output_path, resource_value=123)
                    self.assertFalse(output_path.exists())

    def test_edit_resources_rejects_trailing_payload_before_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.yankai"
            output_path = Path(directory) / "output.yankai"
            input_path.write_bytes(fixture() + b"unexpected")
            with self.assertRaisesRegex(SaveFormatError, "trailing"):
                edit_resources(input_path, output_path, {"money": 1})
            self.assertFalse(output_path.exists())

    def test_validate_save_envelope_rejects_invalid_terminator(self):
        malformed = fixture()[:-1] + b"\x00"
        with self.assertRaisesRegex(SaveFormatError, "terminator"):
            validate_save_envelope(malformed)

    def test_parse_character_types_reports_actionable_error(self):
        self.assertEqual(parse_character_types("0, 5"), frozenset({0, 5}))
        with self.assertRaisesRegex(SaveFormatError, "integer type IDs"):
            parse_character_types("0,nope")


if __name__ == "__main__":
    unittest.main()
