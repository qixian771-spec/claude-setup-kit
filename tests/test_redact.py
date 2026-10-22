"""redact_check.py: public addresses, UUIDs and credentials are hits; placeholders and reserved ranges are not."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import redact_check as rc  # noqa: E402


class ScanLineTests(unittest.TestCase):
    def hits(self, line):
        return rc.scan_line(line)

    def test_reserved_and_known_public_addresses_pass(self):
        for line in ("table <x> { 127.0.0.0/8, 10.0.0.0/8, 224.0.0.0/4, ::1, fe80::/10 }",
                     "server: 203.0.113.10", "nameserver: https://1.1.1.1/dns-query", "https://223.5.5.5/dns-query#DIRECT",
                     "160.79.104.0/21, 2607:6bc0::/32", "resolver 2400:cb00:445:1024::ac46:cd0a", "inet 198.18.0.1"):
            self.assertEqual(self.hits(line), [], line)

    def test_public_addresses_are_hits(self):
        self.assertTrue(any("IPv4" in h for h in self.hits("server: 93.184.216.34")))  # redact-allow: deliberate sample
        self.assertTrue(any("IPv6" in h for h in self.hits("addr 2001:db9::1")))  # redact-allow: deliberate sample

    def test_uuid_and_credentials_are_hits(self):
        self.assertTrue(any("UUID" in h for h in self.hits("uuid: 3c09e6c3-52e9-4601-8ae0-5150fd891b01")))  # redact-allow: deliberate sample
        self.assertTrue(any("凭据" in h for h in self.hits("password: Abc123def456ghi")))  # redact-allow: deliberate sample
        self.assertTrue(any("长随机串" in h for h in self.hits("key = 'q8Zp3Lm9Xy2Vb7Nc4Rt6Wk1Jh5Gd0Fs8Ea2Qw9Zx'")))  # redact-allow: deliberate sample

    def test_placeholders_and_code_identifiers_pass(self):
        for line in ("uuid: {{NODE1_UUID}}", "server: {{NODE1_SERVER}}", "token = self.get_token()",
                     "def test_single_chrome_payload_carries_exactly_the_manifest_policy(self):",
                     "secret = os.environ.get('MIHOMO_SECRET')", "sha256 0ce9ad6a9d4f0829296a72c77d07795dd67f42751e2922be56c051d39ae1c011"):
            self.assertEqual(self.hits(line), [], line)

    def test_private_home_paths_are_hits_except_the_fixture_user(self):
        self.assertTrue(any("私人路径" in h for h in self.hits("STATE = '/Users/alice/Library'")))  # redact-allow: deliberate sample
        self.assertEqual(self.hits("HOME = '/Users/tester'"), [])
        self.assertEqual(self.hits("{{HOME}}/Library/Application Support"), [])


class RepoTests(unittest.TestCase):
    def test_tracked_tree_is_clean(self):
        self.assertEqual(rc.main([]), 0)

    def test_templates_have_no_machine_values(self):
        for path in list((ROOT / "system").rglob("*")) + list((ROOT / "templates").rglob("*")):
            if not path.is_file() or "vendor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for bad in ("niuniu", "/Users/", "utun1024", "丽萨", "出口选择", "user 501"):
                self.assertNotIn(bad, text, str(path))


if __name__ == "__main__":
    unittest.main()
