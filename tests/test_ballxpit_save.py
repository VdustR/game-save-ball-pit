import struct
import tempfile
import unittest
from pathlib import Path

from tools.ballxpit_save import SaveFormatError, count_fields, edit_resources, find_resource_values


def fixture(resources=(4, 10, 20, 30, 40), totals=(4, 100, 200, 300, 400)):
    def field(name, values):
        return struct.pack("<I", len(name)) + name.encode("utf-16le") + b"type-metadata" + b"\x08\x04\x00\x00\x00" + struct.pack("<5i", *values)

    return b"header" + field("NumResources", resources) + field("TotalResources", totals) + b"footer"


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


if __name__ == "__main__":
    unittest.main()
