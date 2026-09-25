from pathlib import Path
import ast
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server" / "assaultfire_server_v143b.py"


def load_server_function(name):
    """Load one pure helper from the server without importing boot-time state."""
    source = SERVER_PATH.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            module = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(module)
            ns = {"struct": struct}
            exec(compile(module, str(SERVER_PATH), "exec"), ns)
            return ns[name]
    raise AssertionError(f"server function not found: {name}")


split_stream = load_server_function("tgame_split_generic_stream")


def make_generic_frame(cmd=0x00, body_len=32, fill=0xA5):
    head_len = 12
    body = bytes([fill]) * body_len
    return (
        b"\x55\x0e"
        + bytes([cmd & 0xFF, 0x04])
        + struct.pack(">I", head_len)
        + struct.pack(">I", body_len)
        + body
    )


def make_synack_frame():
    # Live PH cmd09 shape from the timeout trace:
    # HeadLen=45, BodyLen=16 => 61 total bytes.
    # The 33-byte head extension is [enc_len=32] + 32 encrypted bytes.
    extension = b"\x20" + (b"\xCC" * 32)
    body = b"\xDD" * 16
    head_len = 12 + len(extension)
    return (
        b"\x55\x0e\x09\x04"
        + struct.pack(">I", head_len)
        + struct.pack(">I", len(body))
        + extension
        + body
    )


class TGameTCPStreamTests(unittest.TestCase):
    def test_pre_chgskey_cmd00_and_synack_coalesced(self):
        first = make_generic_frame(cmd=0x00, body_len=32, fill=0x11)
        synack = make_synack_frame()
        frames, tail = split_stream(first + synack)
        self.assertEqual(frames, [first, synack])
        self.assertEqual(tail, b"")

    def test_synack_fragmented_across_recvs(self):
        synack = make_synack_frame()
        frames1, tail1 = split_stream(synack[:17])
        self.assertEqual(frames1, [])
        self.assertEqual(tail1, synack[:17])

        frames2, tail2 = split_stream(tail1 + synack[17:])
        self.assertEqual(frames2, [synack])
        self.assertEqual(tail2, b"")

    def test_synack_and_next_frame_coalesced(self):
        synack = make_synack_frame()
        next_frame = make_generic_frame(cmd=0x00, body_len=48, fill=0x22)
        frames, tail = split_stream(synack + next_frame)
        self.assertEqual(frames, [synack, next_frame])
        self.assertEqual(tail, b"")

    def test_standalone_synack_is_one_complete_frame(self):
        synack = make_synack_frame()
        frames, tail = split_stream(synack)
        self.assertEqual(frames, [synack])
        self.assertEqual(tail, b"")

    def test_server_enables_stream_framing_before_chgskey(self):
        source = SERVER_PATH.read_text(encoding="utf-8", errors="replace")
        self.assertIn(
            'tgame_stream_mode = bool(\n'
            '            role_state.get("tgame") and tgame_mode4_key is not None\n'
            '        )',
            source,
        )
        self.assertIn("tgame_chgskey_complete = True", source)
        self.assertNotIn("post_chgskey_stream_mode = False", source)
        self.assertNotIn("post_chgskey_frame_queue.clear()", source)


if __name__ == "__main__":
    unittest.main()
