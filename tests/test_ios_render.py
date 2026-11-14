"""Tests for scripts/ios_render.py (V2Box Xray JSON, URIs, Stash/Karing YAML, Shadowrocket .conf, QR --serve)."""
import base64
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ios_render as ir  # noqa: E402
import render  # noqa: E402


class IosRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ios-render-test-")
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_dual_node_vless_reality_and_trojan_renders_all_four_formats(self):
        nodes_file = self.root / "nodes.json"
        nodes_data = {
            "NODE1_NAME": "主US",
            "NODE1_SERVER": "us1.example.com",
            "NODE1_PORT": 443,
            "NODE1_UUID": "uid-n1",
            "NODE1_SNI": "www.example.com",
            "NODE1_REALITY_PUBLIC_KEY": "pbk-n1",
            "NODE1_REALITY_SHORT_ID": "ab01",
            "NODE2_TYPE": "ss",
            "NODE2_NAME": "谷歌SS",
            "NODE2_SERVER": "gg.example.com",
            "NODE2_PORT": 8388,
            "NODE2_CIPHER": "aes-256-gcm",
            "NODE2_PASSWORD": "pw-g",
        }
        nodes_file.write_text(json.dumps(nodes_data), encoding="utf-8")
        out_dir = self.root / "out-dual"

        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            code = ir.main(["--nodes", str(nodes_file), "--out", str(out_dir)])
        self.assertEqual(code, 0, err_buf.getvalue())

        # Console stdout must NOT leak any secret host/uuid/password/key
        stdout = out_buf.getvalue()
        for secret in ("us1.example.com", "gg.example.com", "uid-n1", "pbk-n1", "pw-g"):
            self.assertNotIn(secret, stdout)
        self.assertIn("主US", stdout)
        self.assertIn("谷歌SS", stdout)

        # 1. v2box-xray.json
        v2 = json.loads((out_dir / "v2box-xray.json").read_text(encoding="utf-8"))
        self.assertIn("主US+谷歌SS", v2["remarks"])
        self.assertEqual(v2["outbounds"][0]["tag"], "claude-exit")
        self.assertEqual(v2["outbounds"][0]["protocol"], "vless")
        rset = v2["outbounds"][0]["streamSettings"]["realitySettings"]
        self.assertNotIn("support-x25519mlkem768", rset)
        self.assertEqual(rset["publicKey"], "pbk-n1")
        self.assertEqual(v2["outbounds"][1]["tag"], "google-exit")
        self.assertEqual(v2["outbounds"][1]["protocol"], "shadowsocks")
        self.assertEqual(v2["dns"]["queryStrategy"], "UseIPv4")

        v2_rules_txt = json.dumps(v2["routing"]["rules"])
        self.assertNotIn("geosite:geolocation-!cn", v2_rules_txt)
        self.assertNotIn("geosite:anthropic", v2_rules_txt)
        self.assertTrue(any(r.get("ip") == ["::/0"] and r.get("outboundTag") == "block" for r in v2["routing"]["rules"]))
        self.assertTrue(any(r.get("port") == "3478,5349,19302" and r.get("outboundTag") == "block" for r in v2["routing"]["rules"]))

        storage_idx = next(
            i for i, r in enumerate(v2["routing"]["rules"])
            if r.get("outboundTag") == "claude-exit" and "full:storage.googleapis.com" in (r.get("domain") or [])
        )
        google_idx = next(
            i for i, r in enumerate(v2["routing"]["rules"])
            if r.get("outboundTag") == "google-exit" and "domain:googleapis.com" in (r.get("domain") or [])
        )
        self.assertLess(storage_idx, google_idx)

        # 2. v2box-uris.txt
        uris = (out_dir / "v2box-uris.txt").read_text(encoding="utf-8")
        self.assertIn("vless://uid-n1@us1.example.com:443", uris)
        self.assertIn(quote("Claude专用-主US", safe=""), uris)
        self.assertIn("ss://", uris)

        # 3. stash-karing-clash.yaml
        clash_txt = (out_dir / "stash-karing-clash.yaml").read_text(encoding="utf-8")
        self.assertIn("ipv6: false", clash_txt)
        self.assertNotIn("PROCESS-NAME,", clash_txt)
        groups_body = clash_txt.split("\nproxy-groups:", 1)[1].split("\nrules:", 1)[0]
        exit_blk = groups_body.split("- name: 'Google出口'", 1)[0]
        self.assertNotIn("DIRECT", exit_blk)

        # 4. shadowrocket.conf
        sr_txt = (out_dir / "shadowrocket.conf").read_text(encoding="utf-8")
        self.assertIn("ipv6 = false", sr_txt)
        self.assertIn("DEST-PORT,3478,REJECT", sr_txt)
        self.assertIn("FINAL,出口选择", sr_txt)
        self.assertIn("Google出口 = select, 谷歌SS", sr_txt)

    def test_single_node_omits_google_split_across_all_outputs(self):
        nodes_file = self.root / "one.json"
        nodes_file.write_text(json.dumps({
            "NODE1_TYPE": "trojan",
            "NODE1_NAME": "单节点",
            "NODE1_SERVER": "one.example.com",
            "NODE1_PORT": 443,
            "NODE1_PASSWORD": "pw-one",
            "NODE1_SNI": "one.example.com",
        }), encoding="utf-8")
        out_dir = self.root / "out-single"
        res = ir.render_ios_configs(json.loads(nodes_file.read_text(encoding="utf-8")), out_dir)
        self.assertFalse(res["google_split"])

        v2 = json.loads((out_dir / "v2box-xray.json").read_text(encoding="utf-8"))
        tags = [o["tag"] for o in v2["outbounds"]]
        self.assertEqual(tags, ["claude-exit", "direct", "block", "dns-out"])

        clash_txt = (out_dir / "stash-karing-clash.yaml").read_text(encoding="utf-8")
        self.assertNotIn("Google出口", clash_txt.split("\nmixed-port", 1)[1])

        sr_txt = (out_dir / "shadowrocket.conf").read_text(encoding="utf-8")
        self.assertNotIn("Google出口", sr_txt)

    def test_rejects_forbidden_proxy_types_and_existing_dir(self):
        out_dir = self.root / "exists"
        out_dir.mkdir()
        with self.assertRaises(render.RenderError):
            ir.render_ios_configs({"NODE1_PROXY": {"name": "bad", "type": "direct", "server": "a.example.com", "port": 80}}, self.root / "new")
        with self.assertRaises(render.RenderError):
            ir.render_ios_configs({"NODE1_PROXY": {"name": "ok", "type": "trojan", "server": "a.example.com", "port": 443, "password": "pw"}}, out_dir)

    def test_qr_encoder_and_rfc1918_filter(self):
        self.assertTrue(ir._is_rfc1918_lan("192.168.1.25"))
        self.assertTrue(ir._is_rfc1918_lan("10.0.0.8"))
        self.assertTrue(ir._is_rfc1918_lan("172.16.5.4"))
        self.assertFalse(ir._is_rfc1918_lan("198.18.0.1"))  # Clash TUN range must never be picked as LAN
        self.assertFalse(ir._is_rfc1918_lan("100.64.0.1"))  # CGNAT / Tailscale
        self.assertFalse(ir._is_rfc1918_lan("127.0.0.1"))

        mat = ir.qr_matrix("http://192.168.2.103:54321/abcdef012345/")
        self.assertEqual(len(mat), len(mat[0]))
        self.assertEqual(len(mat) % 4, 1)
        # Top-left finder corners must be dark
        self.assertEqual(mat[0][0], 1)
        self.assertEqual(mat[3][3], 1)
        svg = ir.qr_svg("http://192.168.2.103:54321/abcdef012345/")
        self.assertTrue(svg.startswith("<svg ") and svg.endswith("</svg>"))

    def test_import_server_endpoints(self):
        res = ir.render_ios_configs({
            "NODE1_NAME": "主US",
            "NODE1_SERVER": "us1.example.com",
            "NODE1_PORT": 443,
            "NODE1_UUID": "uid-srv",
            "NODE1_SNI": "www.example.com",
            "NODE1_REALITY_PUBLIC_KEY": "pbk-srv",
            "NODE1_REALITY_SHORT_ID": "ab01",
            "NODE2_TYPE": "ss",
            "NODE2_NAME": "谷歌SS",
            "NODE2_SERVER": "gg.example.com",
            "NODE2_PORT": 8388,
            "NODE2_CIPHER": "aes-256-gcm",
            "NODE2_PASSWORD": "pw-g",
        }, self.root / "out-srv")

        server, info = ir.create_import_server(res, lan_ip="127.0.0.1", port=0)
        th = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        th.start()
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen("http://127.0.0.1:%d/wrong-path" % info["port"], timeout=3)
            self.assertEqual(ctx.exception.code, 404)

            head_resp = urlopen(Request(info["pc_url"], method="HEAD"), timeout=3)
            self.assertEqual(head_resp.status, 200)

            pc_html = urlopen(info["pc_url"], timeout=3).read().decode("utf-8")
            self.assertIn("<svg", pc_html)
            self.assertIn("Claude专用-主US", pc_html)
            self.assertIn(info["mobile_url"], pc_html)

            mob_html = urlopen(info["mobile_url"], timeout=3).read().decode("utf-8")
            self.assertIn("v2box://", mob_html)
            self.assertIn("copyRoutesAndOpen", mob_html)
            self.assertIn("v2box://routes?multi=", mob_html)
            self.assertIn("v2box://install-config", mob_html)
            self.assertIn("shadowrocket://config/add/", mob_html)

            routes_uri = ir.build_v2box_routes_scheme()
            routes_data = json.loads(base64.b64decode(routes_uri.split("multi=", 1)[1]).decode("utf-8"))
            self.assertEqual(len(routes_data), 3)
            self.assertTrue(any(r["type"] == "IP" and r["tag"] == "block" and "::/0" in r["listIP"] for r in routes_data))
            self.assertTrue(any(r["type"] == "Domain" and r["tag"] == "direct" and "geosite:cn" in r["list"] for r in routes_data))
            self.assertTrue(any(r["type"] == "IP" and r["tag"] == "direct" and "geoip:cn" in r["listIP"] for r in routes_data))
            self.assertNotIn("geoip:CN", json.dumps(routes_data))

            sub_b64 = urlopen(info["sub_url"], timeout=3).read().decode("utf-8")
            decoded = base64.b64decode(sub_b64).decode("utf-8")
            self.assertIn("vless://uid-srv@us1.example.com:443", decoded)
            self.assertIn(quote("Claude专用-主US", safe=""), decoded)
            self.assertIn("ss://", decoded)

            sr_conf = urlopen(info["shadowrocket_url"], timeout=3).read().decode("utf-8")
            self.assertIn("[General]", sr_conf)
            self.assertIn("ipv6 = false", sr_conf)
        finally:
            server.shutdown()
            server.server_close()
            th.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
