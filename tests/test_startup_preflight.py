from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import assaultfire_preflight as preflight


class StartupPreflightTests(unittest.TestCase):
    def build_fixture(self, tmp: Path):
        client_root = tmp / "AF"
        tcls_dir = client_root / "TCLS" / "Tenio"
        config_dir = client_root / "TCLS" / "config"
        tcls_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)

        tcls_bytes = b"validated-test-tcls"
        tcls_path = tcls_dir / "TCLS.dll"
        tcls_path.write_bytes(tcls_bytes)
        validated_hash = hashlib.sha256(tcls_bytes).hexdigest()

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        private_path = tmp / "PRIVATE.PEM"
        private_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        (config_dir / "APClient.dat").write_bytes(public_pem)

        hosts_path = tmp / "hosts"
        hosts_path.write_text(
            "\n".join(
                f"127.0.0.1 {name}" for name in preflight.REQUIRED_HOSTS
            ) + "\n",
            encoding="utf-8",
        )
        return client_root, private_path, hosts_path, validated_hash, public_pem

    def test_all_required_checks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            data = self.build_fixture(Path(td))
            client_root, private_path, hosts_path, validated_hash, _ = data
            report = preflight.evaluate_preflight(
                private_key_path=private_path,
                client_root=client_root,
                hosts_path=hosts_path,
                resolver=lambda _name: "127.0.0.1",
                validated_tcls_sha256=validated_hash,
            )
            self.assertTrue(report.ok, report.errors)
            self.assertTrue(report.key_check.exact_bytes_match)
            self.assertTrue(report.key_check.same_rsa_key)
            self.assertEqual(report.key_check.rsa_key_size, 1024)
            self.assertEqual(report.key_check.apclient_length, 272)

    def test_same_rsa_key_is_not_enough_when_bytes_differ(self):
        with tempfile.TemporaryDirectory() as td:
            data = self.build_fixture(Path(td))
            client_root, private_path, hosts_path, validated_hash, public_pem = data
            apclient = client_root / "TCLS" / "config" / "APClient.dat"
            apclient.write_bytes(public_pem.replace(b"\n", b"\r\n"))
            report = preflight.evaluate_preflight(
                private_key_path=private_path,
                client_root=client_root,
                hosts_path=hosts_path,
                resolver=lambda _name: "127.0.0.1",
                validated_tcls_sha256=validated_hash,
            )
            self.assertFalse(report.ok)
            self.assertFalse(report.key_check.exact_bytes_match)
            self.assertTrue(report.key_check.same_rsa_key)

    def test_bad_hosts_mapping_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            data = self.build_fixture(Path(td))
            client_root, private_path, hosts_path, validated_hash, _ = data
            hosts_path.write_text(
                "127.0.0.1 tversion.levelupgames.ph\n"
                "10.0.0.5 tauthproxy.levelupgames.ph\n"
                "127.0.0.1 tdir.levelupgames.ph\n",
                encoding="utf-8",
            )
            report = preflight.evaluate_preflight(
                private_key_path=private_path,
                client_root=client_root,
                hosts_path=hosts_path,
                resolver=lambda name: "10.0.0.5" if name.startswith("tauth") else "127.0.0.1",
                validated_tcls_sha256=validated_hash,
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("tauthproxy.levelupgames.ph" in e for e in report.errors))

    def test_server_calls_preflight_before_listener_threads(self):
        server = (ROOT / "server" / "assaultfire_server_v143b.py").read_text(
            encoding="utf-8", errors="replace"
        )
        main = server.index('if __name__ == "__main__":')
        gate = server.index("run_server_preflight(Path(PRIVATE_KEY_PATH))", main)
        listener = server.index("threading.Thread(", main)
        self.assertLess(gate, listener)


if __name__ == "__main__":
    unittest.main()
