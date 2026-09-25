from pathlib import Path
import importlib.util
import json
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AFRE_PATH = ROOT / "tools" / "research" / "afre.py"
CATALOG_PATH = ROOT / "tools" / "research" / "af_symbols_10024.json"

spec = importlib.util.spec_from_file_location("afre", AFRE_PATH)
afre = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(afre)


def make_minimal_pe(path: Path) -> None:
    pe_off = 0x80
    opt_size = 0xE0
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_off)
    data[pe_off:pe_off + 4] = b"PE\0\0"
    struct.pack_into(
        "<HHIIIHH", data, pe_off + 4, 0x14C, 1, 0, 0, 0, opt_size, 0x010F
    )
    opt = pe_off + 24
    struct.pack_into("<H", data, opt, 0x10B)
    struct.pack_into("<I", data, opt + 16, 0x1234)
    struct.pack_into("<I", data, opt + 28, 0x00400000)
    struct.pack_into("<I", data, opt + 56, 0x00300000)
    sec = opt + opt_size
    data[sec:sec + 8] = b".text\0\0\0"
    struct.pack_into("<IIII", data, sec + 8, 0x2000, 0x1000, 0x600, 0x200)
    struct.pack_into("<I", data, sec + 36, 0x60000020)
    path.write_bytes(data)


class AfreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = afre.load_catalog(CATALOG_PATH)

    def test_catalog_build_identity(self):
        self.assertEqual(self.catalog["schema_version"], 1)
        self.assertEqual(
            self.catalog["build"]["sha256"],
            "b4273f2658ca94eebc559a997fdfcd02"
            "d51e77ce75b892250c1db7fb80c70b51",
        )

    def test_lookup_known_symbol(self):
        group, name, meta = afre.lookup_symbol(self.catalog, "GWorld")
        self.assertEqual((group, name), ("globals", "GWorld"))
        self.assertEqual(afre.parse_int(meta["va"]), 0x02066BF8)

    def test_nearest_symbol(self):
        group, name, _, delta = afre.nearest_symbol(self.catalog, 0x00DA2765)
        self.assertEqual(
            (group, name, delta), ("functions", "UWorld_SetGameInfo", 5)
        )

    def test_layout_known_offset(self):
        value = self.catalog["layouts"]["APlayerController"]["Player"]["offset"]
        self.assertEqual(afre.parse_int(value), 0x66C)

    def test_parse_minimal_pe(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.exe"
            make_minimal_pe(path)
            pe = afre.parse_pe(path)
        self.assertEqual(pe["machine"], 0x14C)
        self.assertEqual(pe["image_base"], 0x00400000)
        self.assertEqual(pe["entry_rva"], 0x1234)
        self.assertEqual(pe["number_of_sections"], 1)
        self.assertEqual(pe["sections"][0]["name"], ".text")
        self.assertEqual(pe["sections"][0]["va"], 0x00401000)


    def test_annotate_text(self):
        source = "crash at 0x00DA2765\n"
        annotated = afre.annotate_text(source, self.catalog)
        self.assertIn(
            "0x00DA2765=functions.UWorld_SetGameInfo+0x5",
            annotated,
        )

    def test_json_diff(self):
        changes = afre.diff_json(
            {"graph": {"count": 1}, "same": 7},
            {"graph": {"count": 2}, "same": 7},
        )
        self.assertEqual(changes, [("graph.count", 1, 2)])

    def test_loader_constant_extract(self):
        with tempfile.TemporaryDirectory() as td:
            loader = Path(td) / "loader.py"
            loader.write_text(
                "GIS_EDITOR_VA = 0x01FD69AC\n"
                "GIS_CLIENT_VA = 0x01FD69C8\n"
                "GIS_SERVER_VA = 0x01FD69CC\n",
                encoding="utf-8",
            )
            constants = afre.extract_int_constants(loader)
        self.assertEqual(constants["GIS_EDITOR_VA"], 0x01FD69AC)
        self.assertEqual(constants["GIS_CLIENT_VA"], 0x01FD69C8)



    def test_catalog_audit(self):
        self.assertEqual(afre.catalog_errors(self.catalog), [])

    def test_idc_label_export(self):
        output = afre.render_labels(self.catalog, "idc")
        self.assertIn(
            'set_name(0x02066BF8, "globals__GWorld", SN_NOWARN);',
            output,
        )

    def test_csv_label_export(self):
        output = afre.render_labels(self.catalog, "csv")
        self.assertIn(
            "0x02066BF8,globals,GWorld,globals__GWorld,verified",
            output,
        )



    def test_object_database_loads(self):
        db = afre.load_object_db(ROOT / "tools" / "research" / "af_objects_10024.json")
        self.assertEqual(db["schema_version"], 1)
        self.assertEqual(afre.object_db_errors(db, self.catalog), [])

    def test_lookup_pve_player_controller_object(self):
        db = afre.load_object_db(ROOT / "tools" / "research" / "af_objects_10024.json")
        group, name, meta = afre.lookup_object(db, "PVEPlayerController")
        self.assertEqual((group, name), ("objects", "PVEPlayerController"))
        self.assertEqual(
            afre.parse_int(meta["fields"]["PlayerReplicationInfo"]["offset"]),
            0x1DC,
        )

    def test_object_database_records_controller_conflict(self):
        db = afre.load_object_db(ROOT / "tools" / "research" / "af_objects_10024.json")
        conflicts = {item["id"]: item for item in db["conflicts"]}
        item = conflicts["APlayerController_player_camera_ack_layout"]
        variants = {v["name"]: v for v in item["variants"]}
        self.assertEqual(
            variants["live_pve_controller"]["fields"]["Player"], "0x370"
        )
        self.assertEqual(
            variants["current_afdevloader_a_player_controller"]["fields"]["Player"],
            "0x66C",
        )

    def test_promoted_reflection_symbols(self):
        group, name, meta = afre.lookup_symbol(self.catalog, "UObject_ProcessEvent")
        self.assertEqual((group, name), ("functions", "UObject_ProcessEvent"))
        self.assertEqual(afre.parse_int(meta["va"]), 0x00483440)


    def test_catalog_is_plain_json(self):
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertIn("symbols", data)
        self.assertIn("layouts", data)


if __name__ == "__main__":
    unittest.main()
