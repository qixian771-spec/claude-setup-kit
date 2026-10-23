# 交付记录：claude-setup-kit 0.1.0（macOS）

方案与逐卡验收（含证据）在参考机的研究目录 `research/claude-env-mirror-2026-10-22/方案与任务卡.md`；本文是仓库内的摘要。

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| E1 | `manifest.json` 36 个组件；只读 `scripts/mirror_check.py`（退出 0/1/2，`--json --only --param --no-network`，系统 Python 3.9）；53 个夹具测试 | 通过：参考机唯一 ❌ 是 Chrome 策略 |
| E2 | Chrome 策略改用描述文件 `installers/Chrome策略.mobileconfig`（手工写 Managed Preferences 会被系统清掉） | 通过：chrome://policy 平台/强制/正常；ippure WebRTC 未泄露、DNS 全部国外 |
| E3 | `system/` 与 `templates/` 占位符模板、`scripts/render.py`、`installers/lib` 7 组安装/卸载 + 双击 `.command`、`tools/redact_check.py` | 通过：脱敏 0 命中；安装器对已装组件全部拒绝覆盖（exit 72）；卸载往返未在参考机原生验证 |
| E4 | SKILL、README、执行手册（S1–S12，每步对应组件 id，22 条情景推演）、对话模板、ippure 验收说明、`tools/check.py`、CI | 本提交 |
| E5 | 公开仓库发布、CI 绿、vps 仓库 macos-leak-guard.md 改为对照与链接 | 通过：run 39874114255；vps run 39873953681 |
| E6 | 总入口：仓库改名 claude-setup-kit；README“发给 AI 的一段话”；START.md 四条路线；manifest `steps`；`next_step.py`；另两仓库 README 指回 | 通过：run 39874984538 / 39875414828；Haiku 只读推演按那段话走通并找出两处缺口（已修） |

## 已知边界

- 参考机的 `sudo` 是全免密，仓库里给别人的 sudoers 规则是最小集；两者行为一致但权限范围不同。
- 共用 CDN 的 Claude 域名（downloads.claude.ai、statsig、status）靠 Clash 规则，PF 墙不覆盖。
- Firefox 没有策略模板；Safari 靠 PF UID 规则。
- 语言顺序只记录不改；字体无法改。

## 0.2.0 Windows 10/11（计划，W1–W6）

方案与任务卡在参考机研究目录 `research/claude-env-mirror-2026-10-22/Windows方案与任务卡.md`：防火墙规则（`New-NetFirewallRule -InterfaceAlias/-LocalUser`）代替 PF，计划任务代替 LaunchDaemon，`.reg` 代替描述文件（Chrome + Edge），`tzutil` 时区；Windows 侧不做精确 IP 更新器。实机验收在用户的局域网 Windows 机器上，写操作仍由用户双击 `.cmd`。
