from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from assaultfire_room_registry import RoomRegistry, RoomRegistryError
from assaultfire_ds_spawner import DedicatedServerSpawner, SpawnerConfig


class RoomRegistryConsistencyTests(unittest.TestCase):
    def make_room(self, registry: RoomRegistry, owner=10000):
        return registry.create_room(
            {
                "room_id": 1,
                "display_id": 1,
                "name": "test",
                "fighter_capacity": 4,
                "observer_capacity": 0,
                "password": "",
                "match_settings_wire": b"",
                "mode_id": 0x2001,
                "map_id": 0x2F,
                "sub_mode_id": 0x1001,
                "flags": 0x3008,
            },
            owner_uin=owner,
            owner_name=f"P{owner}",
        )

    def test_join_rollback_removes_new_member(self):
        registry = RoomRegistry()
        self.make_room(registry)
        registry.join_room(
            uin=20000,
            nickname="P20000",
            room_id=1,
            password="",
            observer=False,
        )
        self.assertIsNotNone(registry.room_for_player(20000))
        self.assertTrue(registry.rollback_join(20000, 1))
        self.assertIsNone(registry.room_for_player(20000))
        room = registry.get_room(1)
        self.assertEqual([m["uin"] for m in room["members"]], [10000])

    def test_only_owner_is_authorized_for_owner_actions(self):
        registry = RoomRegistry()
        self.make_room(registry)
        registry.join_room(
            uin=20000,
            nickname="P20000",
            room_id=1,
            password="",
            observer=False,
        )
        registry.require_owner(1, 10000)
        with self.assertRaises(RoomRegistryError):
            registry.require_owner(1, 20000)

    def test_registry_chosen_owner_is_applied_to_spawner(self):
        registry = RoomRegistry()
        self.make_room(registry, owner=10000)
        registry.join_room(
            uin=30000,
            nickname="seat1",
            room_id=1,
            password="",
            observer=False,
        )
        registry.join_room(
            uin=20000,
            nickname="seat2",
            room_id=1,
            password="",
            observer=False,
        )

        with tempfile.TemporaryDirectory() as td:
            cfg = SpawnerConfig(
                enabled=True,
                max_instances=1,
                public_port_base=0,
                target_port_base=0,
                runtime_dir=Path(td) / "runtime",
                create_cooldown=0.0,
            )
            spawner = DedicatedServerSpawner(cfg)
            allocation = spawner.reserve_lobby(owner_id=10000)
            self.assertEqual(allocation.room_id, 1)
            spawner.register_room_player(1, 30000)
            spawner.register_room_player(1, 20000)

            left = registry.leave_room(10000)
            # Lowest seat wins in the registry: 30000 is seat 1, while 20000 is seat 2.
            self.assertEqual(left["new_owner_uin"], 30000)

            result = spawner.remove_room_player(
                1,
                10000,
                authoritative_new_owner=left["new_owner_uin"],
            )
            self.assertEqual(result["owner_id"], 30000)
            self.assertEqual(spawner.allocation_for_room(1).owner_id, 30000)

    def test_spawner_refuses_to_guess_owner_transfer(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = SpawnerConfig(
                enabled=True,
                max_instances=1,
                public_port_base=0,
                target_port_base=0,
                runtime_dir=Path(td) / "runtime",
                create_cooldown=0.0,
            )
            spawner = DedicatedServerSpawner(cfg)
            spawner.reserve_lobby(owner_id=10000)
            spawner.register_room_player(1, 20000)
            with self.assertRaises(Exception):
                spawner.remove_room_player(1, 10000)
            # Validation happens before mutation.
            self.assertIn(10000, spawner.allocation_for_room(1).room_players)


class ServerStaticSafetyTests(unittest.TestCase):
    def test_auth_hex_is_debug_only(self):
        server = (ROOT / "server" / "assaultfire_server_v143b.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("AF_DEBUG_AUTH_HEX", server)
        needle = 'f"AP RX plaintext {len(plaintext)}B: {plaintext.hex()}"'
        pos = server.index(needle)
        context = server[max(0, pos - 300):pos]
        self.assertIn("if DEBUG_AUTH_HEX:", context)
        self.assertIn('"AUTH-DEBUG"', context)

    def test_a10a_has_reservation_rollback(self):
        server = (ROOT / "server" / "assaultfire_server_v143b.py").read_text(
            encoding="utf-8", errors="replace"
        )
        create = server.index('elif app["cmd"] == TGAME_ZN_REQ_CREATEMATCHROOM:')
        next_handler = server.index('elif app["cmd"] == TGAME_ZN_REQ_ENTERMATCHROOM:', create)
        block = server[create:next_handler]
        self.assertIn("player-already-in-room", block)
        self.assertIn("V143B_DS_SPAWNER.release_lobby", block)
        self.assertIn("A10A registry/create rollback", block)

    def test_owner_checks_guard_settings_and_start_paths(self):
        server = (ROOT / "server" / "assaultfire_server_v143b.py").read_text(
            encoding="utf-8", errors="replace"
        )
        for marker in (
            'elif app["cmd"] == TGAME_ZN_REQ_SETGAMESETTINGS:',
            'elif app["cmd"] == TGAME_ZN_REQ_STARTMATCH:',
            'elif app["cmd"] == TGAME_ZN_REQ_STARTROOMALLOC:',
        ):
            start = server.index(marker)
            block = server[start:start + 7000]
            self.assertIn("V150_ROOM_REGISTRY.require_owner", block)


if __name__ == "__main__":
    unittest.main()
