"""Static checks on files the user installs by double-click. Nothing is installed here."""
import json
import plistlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


class ChromeProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = plistlib.loads((ROOT / "installers" / "Chrome策略.mobileconfig").read_bytes())

    def test_identifier_matches_manifest_param(self):
        self.assertEqual(self.profile["PayloadIdentifier"], MANIFEST["params"]["chrome_profile_identifier"])
        self.assertEqual(self.profile["PayloadScope"], "System")
        self.assertEqual(self.profile["PayloadType"], "Configuration")
        self.assertFalse(self.profile["PayloadRemovalDisallowed"])

    def test_single_chrome_payload_carries_exactly_the_manifest_policy(self):
        payloads = self.profile["PayloadContent"]
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["PayloadType"], "com.google.Chrome")
        policy = {k: v for k, v in payload.items() if not k.startswith("Payload")}
        self.assertEqual(policy, MANIFEST["params"]["chrome_policy"])

    def test_uuids_are_stable(self):
        self.assertNotEqual(self.profile["PayloadUUID"], self.profile["PayloadContent"][0]["PayloadUUID"])
        for value in (self.profile["PayloadUUID"], self.profile["PayloadContent"][0]["PayloadUUID"]):
            self.assertRegex(value, r"^[0-9A-F]{8}-[0-9A-F]{4}-5[0-9A-F]{3}-[0-9A-F]{4}-[0-9A-F]{12}$")


if __name__ == "__main__":
    unittest.main()
