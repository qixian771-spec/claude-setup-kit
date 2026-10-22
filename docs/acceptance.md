# 验收记录

## 参考机（2026-10-22）

- E1：`python3 scripts/mirror_check.py` → `合计: ✅ 33 ❌ 1 ❓ 0 ℹ️ 1 👉 1 → exit 1`，唯一 ❌ `chrome.policy`。
- E2：装描述文件后 `合计: ✅ 34 ❌ 0 ❓ 0 ℹ️ 1 👉 1 → exit 0`；chrome://policy 两条策略 平台/强制/正常；ippure：claude.com / claude.ai 出口同一美国 IP，WebRTC 未发现真实 IP 泄露，5 个解析器全部 Cloudflare 美国。
- E3：三个 PF 锚点渲染后 `pfctl -n` 通过；Clash 模板渲染 → 用户脚本模拟生成 → `verge-mihomo -t` 通过；7 个安装脚本对已装组件全部 `已存在，拒绝覆盖`（exit 72），系统文件 mtime 指纹不变；`tools/redact_check.py` 0 命中。
- 未原生验证：卸载往返（参考机不能卸正在用的防护）；N7 式的"出口切换告警"（出口固定不切）。

## GitHub CI

E5 发布后在此记录 run 编号与结论。
