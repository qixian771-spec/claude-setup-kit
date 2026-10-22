# 验收记录

## 参考机（2026-10-22）

- E1：`python3 scripts/mirror_check.py` → `合计: ✅ 33 ❌ 1 ❓ 0 ℹ️ 1 👉 1 → exit 1`，唯一 ❌ `chrome.policy`。
- E2：装描述文件后 `合计: ✅ 34 ❌ 0 ❓ 0 ℹ️ 1 👉 1 → exit 0`；chrome://policy 两条策略 平台/强制/正常；ippure：claude.com / claude.ai 出口同一美国 IP，WebRTC 未发现真实 IP 泄露，5 个解析器全部 Cloudflare 美国。
- E3：三个 PF 锚点渲染后 `pfctl -n` 通过；Clash 模板渲染 → 用户脚本模拟生成 → `verge-mihomo -t` 通过；7 个安装脚本对已装组件全部 `已存在，拒绝覆盖`（exit 72），系统文件 mtime 指纹不变；`tools/redact_check.py` 0 命中。
- 未原生验证：卸载往返（参考机不能卸正在用的防护）；N7 式的"出口切换告警"（出口固定不切）。

## GitHub CI（2026-10-22）

- 仓库：<https://github.com/qixian771-spec/claude-mac-env-mirror>（公开）。
- `699c2c5`：[run 39874114255](https://github.com/qixian771-spec/claude-mac-env-mirror/actions/runs/39874114255) 三个 job 全部通过：ubuntu 3.9 / 3.12 与 macos-14 3.12 的 check.py、redact_check、81 项测试；macOS 原生只读 smoke（mirror_check 在空 runner 上 exit 1 不崩、7 个组件渲染、`pfctl -n`、`plutil -lint`）。
- 之前三轮失败均为 runner 环境差异（无 uid 501、bash -e 中止、无 Wi-Fi 服务），逐一修正，见 docs/release-tasks.md。
- vps-node-rebuild-3xui `ddde001`（macos-leak-guard.md 改为对照与链接）：run 39873953681 四个 job 全部通过。
