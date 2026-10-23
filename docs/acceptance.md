# 验收记录

## 参考机（2026-10-22）

- E1：`python3 scripts/mirror_check.py` → `合计: ✅ 33 ❌ 1 ❓ 0 ℹ️ 1 👉 1 → exit 1`，唯一 ❌ `chrome.policy`。
- E2：装描述文件后 `合计: ✅ 34 ❌ 0 ❓ 0 ℹ️ 1 👉 1 → exit 0`；chrome://policy 两条策略 平台/强制/正常；ippure：claude.com / claude.ai 出口同一美国 IP，WebRTC 未发现真实 IP 泄露，5 个解析器全部 Cloudflare 美国。
- E3：三个 PF 锚点渲染后 `pfctl -n` 通过；Clash 模板渲染 → 用户脚本模拟生成 → `verge-mihomo -t` 通过；7 个安装脚本对已装组件全部 `已存在，拒绝覆盖`（exit 72），系统文件 mtime 指纹不变；`tools/redact_check.py` 0 命中。
- 未原生验证：卸载往返（参考机不能卸正在用的防护）；N7 式的"出口切换告警"（出口固定不切）。

## GitHub CI（2026-10-22）

- 仓库：<https://github.com/qixian771-spec/claude-setup-kit>（公开）。
- `699c2c5`：[run 39874114255](https://github.com/qixian771-spec/claude-setup-kit/actions/runs/39874114255) 三个 job 全部通过：ubuntu 3.9 / 3.12 与 macos-14 3.12 的 check.py、redact_check、81 项测试；macOS 原生只读 smoke（mirror_check 在空 runner 上 exit 1 不崩、7 个组件渲染、`pfctl -n`、`plutil -lint`）。
- 之前三轮失败均为 runner 环境差异（无 uid 501、bash -e 中止、无 Wi-Fi 服务），逐一修正，见 docs/release-tasks.md。
- vps-node-rebuild-3xui `ddde001`（macos-leak-guard.md 改为对照与链接）：run 39873953681 四个 job 全部通过。

## E6 弱模型推演（2026-10-22）

Haiku 子代理只拿 README 的"发给 AI 的一段话"，在去掉卸载脚本的临时克隆里做只读部分：读 START.md → `mirror_check`（33 ✅ / 1 ❌）→ 问路线并（按预设）得到 B → `next_step`（S7，因克隆里没有 mirror.params.json，ipv6 守护 label 用了默认值）→ 准备让用户双击、不越界。它指出两处缺口：START.md 第 0 步没要求写 mirror.params.json；S7 话术没提输密码。两处已修（`fb85ee4`，CI run 39875414828 success）。

## W1 Windows 对账（2026-10-22）

- 局域网 Win10 19045 实机只读：`py -3 scripts\mirror_check.py --no-network --param network_services=以太网` → exit 1，✅1 ❌13 ❓8（Clash 未运行：命名管道不可达；`--no-network`）ℹ️2 👉1，无 Traceback；`clash.dns`、`wf.enabled`（只开 Private）、`sys.timezone`（China Standard Time）抓到的都是真实状态。
- CI：`216fef0`/`beff452` 的 run 39876657822 macOS 通过、ubuntu 两个 job 失败——Linux runner 上 `platform_key()` 返回 `linux`，next_step 按该平台筛不到任何组件而报错；已改为非 Windows 一律用 macOS 组件表（后续 run 见下）。
- 发现并修复：作为 `__main__` 运行时 `winchecks` 的 `import mirror_check` 是另一个模块对象，`HostError` 不相等导致 ❌ 被报成 ❓；已绑定并加回归测试。
