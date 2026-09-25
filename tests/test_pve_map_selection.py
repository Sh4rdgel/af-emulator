from pathlib import Path
import unittest

from server.assaultfire_ds_spawner import AFDEV_MODE_IDS, ROOM_TARGETS, resolve_room_target

ROOT = Path(__file__).resolve().parents[1]


class PVEMapSelectionTests(unittest.TestCase):
    def text(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")

    def test_client_map_is_enabled_by_default(self):
        server = self.text("server/assaultfire_server_v143b.py")
        self.assertIn('AF_DS_USE_CLIENT_MAP", "1"', server)
        self.assertIn('client_map = str(create_req.get("map_string") or "").strip()', server)

    def test_a10a_seeds_full_ds_settings(self):
        server = self.text("server/assaultfire_server_v143b.py")
        for marker in (
            'map_name=map_name',
            'mode_id=int(create_req.get("mode_id", 0x00002001))',
            'map_id=int(create_req.get("map_id", 0x002F))',
            'sub_mode_id=int(create_req.get("sub_mode_id", 0x00001001))',
            'room_flags=int(create_req.get("flags", 0x00003008))',
        ):
            self.assertIn(marker, server)

    def test_a11e_updates_reserved_map_before_lazy_spawn(self):
        server = self.text("server/assaultfire_server_v143b.py")
        spawner = self.text("server/assaultfire_ds_spawner.py")
        self.assertIn('map_name=settings.get("map_string") or None', server)
        self.assertIn('map_name: Optional[str] = None', spawner)
        self.assertIn('allocation.map_name = desired_map or verified_map', spawner)
        self.assertIn('"--map", allocation.map_name', spawner)
        self.assertIn('"--game", allocation.game_class', spawner)

    def test_defense_steel_forest_empty_mapstring_uses_verified_target(self):
        self.assertIn(0x00002002, AFDEV_MODE_IDS)
        self.assertEqual(
            ROOM_TARGETS[(0x00002002, 0x0010)],
            ("IF-Factory_3_Main", "PVEGame.TGIFGame"),
        )
        self.assertEqual(
            resolve_room_target(0x00002002, 0x0010, "", "PVEGame.TGSVGame"),
            ("IF-Factory_3_Main", "PVEGame.TGIFGame"),
        )

    def test_server_routes_verified_afdev_modes_without_dead_legacy_fallback(self):
        server = self.text("server/assaultfire_server_v143b.py")
        self.assertIn("TGAME_AFDEV_MODE_IDS = frozenset(AFDEV_MODE_IDS)", server)
        self.assertIn("mode_now not in TGAME_AFDEV_MODE_IDS", server)
        self.assertNotIn("ZN2C_NTF_STARTMATCH legacy-non-PVE", server)

    def test_afdev_loader_accepts_defense_settings_family(self):
        loader = self.text(
            "tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py"
        )
        self.assertIn('0x00002001: "Survival"', loader)
        self.assertIn('0x00002002: "Defense"', loader)
        self.assertIn("unsupported AFDEV ModeId", loader)
        self.assertNotIn(
            'PvE loader expected ModeId 0x2001',
            loader,
        )

    def test_defense_does_not_require_survival_gri_difficulty_field(self):
        loader = self.text(
            "tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py"
        )
        self.assertIn(
            "if mode_id == 0x00002001:",
            loader,
        )
        self.assertIn(
            "Defense GRI difficulty write skipped",
            loader,
        )
        self.assertIn(
            '"difficulty_applied": difficulty_applied',
            loader,
        )



if __name__ == "__main__":
    unittest.main()
