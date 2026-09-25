from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from assaultfire_logging import AFLogger, FILE_CAPTURE_LEVEL


class ServerLoggingTests(unittest.TestCase):
    def emit_with_console(self, logger, records):
        output = StringIO()
        with redirect_stdout(output):
            for level, message in records:
                logger.emit("TEST", message, level=level)
        return output.getvalue()

    def test_file_always_keeps_debug_when_console_is_info(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "server.log"
            logger = AFLogger(console_level_name="INFO", path=path)

            console = self.emit_with_console(
                logger,
                [
                    ("DEBUG", "debug-detail"),
                    ("INFO", "normal-info"),
                ],
            )

            self.assertNotIn("debug-detail", console)
            self.assertIn("normal-info", console)

            saved = path.read_text(encoding="utf-8")
            self.assertIn("[DEBUG] [TEST] debug-detail", saved)
            self.assertIn("[INFO] [TEST] normal-info", saved)

    def test_warning_console_still_saves_debug_and_info(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "server.log"
            logger = AFLogger(console_level_name="WARNING", path=path)

            console = self.emit_with_console(
                logger,
                [
                    ("DEBUG", "debug-detail"),
                    ("INFO", "normal-info"),
                    ("WARNING", "visible-warning"),
                    ("ERROR", "visible-error"),
                ],
            )

            self.assertNotIn("debug-detail", console)
            self.assertNotIn("normal-info", console)
            self.assertIn("visible-warning", console)
            self.assertIn("visible-error", console)

            saved = path.read_text(encoding="utf-8")
            for message in (
                "debug-detail",
                "normal-info",
                "visible-warning",
                "visible-error",
            ):
                self.assertIn(message, saved)

    def test_debug_console_prints_every_level(self):
        with tempfile.TemporaryDirectory() as td:
            logger = AFLogger(
                console_level_name="DEBUG",
                path=Path(td) / "server.log",
            )
            console = self.emit_with_console(
                logger,
                [
                    ("DEBUG", "d"),
                    ("INFO", "i"),
                    ("WARNING", "w"),
                    ("ERROR", "e"),
                ],
            )
            for marker in ("[DEBUG]", "[INFO]", "[WARNING]", "[ERROR]"):
                self.assertIn(marker, console)

    def test_file_capture_floor_is_debug(self):
        self.assertEqual(FILE_CAPTURE_LEVEL, "DEBUG")

    def test_default_server_log_path_and_spawner_routing_are_explicit(self):
        logging_source = (ROOT / "server" / "assaultfire_logging.py").read_text(
            encoding="utf-8", errors="replace"
        )
        server = (ROOT / "server" / "assaultfire_server_v143b.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('with_name("af_server_live.log")', logging_source)
        self.assertIn(
            "DedicatedServerSpawner(V143B_DS_CONFIG, log_fn=log)",
            server,
        )
        self.assertIn(
            'log("BOOT", f"Persistent server log: {_SERVER_LOGGER.path}")',
            server,
        )
        self.assertIn('"DS-REJOIN"', server)

    def test_invalid_console_level_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                AFLogger(
                    console_level_name="EVERYTHING",
                    path=Path(td) / "server.log",
                )


class SensitiveDebugStaticTests(unittest.TestCase):
    def test_raw_auth_hex_remains_explicit_opt_in(self):
        server = (ROOT / "server" / "assaultfire_server_v143b.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("AF_DEBUG_AUTH_HEX", server)
        for needle in (
            "AP RX plaintext",
            "AP RX encrypted",
            "AP RX second plaintext",
        ):
            pos = server.index(needle)
            context = server[max(0, pos - 500):pos + 300]
            self.assertIn("DEBUG_AUTH_HEX", context)
            self.assertIn('level="DEBUG"', context)


if __name__ == "__main__":
    unittest.main()
