from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PVERuntimeTests(unittest.TestCase):
    def text(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")

    def test_server_uses_lazy_ds_start_flow(self):
        s = self.text("server/assaultfire_server_v143b.py")
        self.assertIn("A10A reserve only", s)
        self.assertIn("A3A0/A113 arm bridge + A11A", s)
        self.assertIn("0xA11E", s)

    def test_loader_requires_verified_ready_state(self):
        s = self.text("tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py")
        self.assertIn("SESSION_READY", s)
        self.assertIn("zero_dskey", s)
        self.assertIn("native_movement", s)

    def test_multi_peer_bridge_is_present(self):
        s = self.text("tools/bridge/af_ds_udp_bridge_v9_multi_peer_latch.py")
        self.assertIn("SESSION_READY", s)
        self.assertIn("peer", s.lower())

    def test_player_scoped_cleanup_is_present(self):
        s = self.text("server/assaultfire_ds_spawner.py")
        for marker in ("room_players", "match_players", "ROUND_ENDED"):
            self.assertIn(marker, s)

    def test_active_pve_path_has_no_fixed_install_or_map_fallback(self):
        spawner = self.text("server/assaultfire_ds_spawner.py")
        bridge = self.text("tools/bridge/af_ds_udp_bridge_v9_multi_peer_latch.py")
        loader = self.text("tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py")
        self.assertIn('game_dir: str = ""', spawner)
        self.assertIn('default_map: str = ""', spawner)
        self.assertIn('os.environ.get("AF_GAME_DIR", "")', bridge)
        self.assertIn('os.environ.get("AF_DS_DEFAULT_MAP", "")', bridge)
        self.assertIn('os.environ.get("AF_GAME_DIR", "")', loader)
        self.assertIn('os.environ.get("AF_DS_DEFAULT_MAP", "")', loader)
        self.assertIn("AF_GAME_DIR is not set", spawner)
        self.assertIn("no PvE map was selected", spawner)

if __name__ == "__main__":
    unittest.main()
