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
| E7 | Google 专用分组通用化：Clash 模板照参考机现状重生成（112 条规则、`{{GOOGLE_GROUP}}` 成员为主出口以外的节点占位符、Google 后缀规则在 storage/fonts 之后、GEOSITE 之前）；新组件 `clash.google_exit`（分组存在、无 DIRECT、当前节点≠Claude 出口、规则顺序）；手册/START/对话模板说明 Google 把机房 IP 判成中国的问题 | 通过：参考机对账 ✅；渲染+脚本模拟后 `verge-mihomo -t` 通过；130 例 |

## 已知边界

- 参考机的 `sudo` 是全免密，仓库里给别人的 sudoers 规则是最小集；两者行为一致但权限范围不同。
- 共用 CDN 的 Claude 域名（downloads.claude.ai、statsig、status）靠 Clash 规则，PF 墙不覆盖。
- Firefox 没有策略模板；Safari 靠 PF UID 规则。
- 语言顺序只记录不改；字体无法改。

## 0.2.0 Windows 10/11（W1–W6）

决定（用户，2026-10-22）：Windows 侧不做精确 IP 更新器（整段墙 + Clash 域名规则）；实机验收用用户局域网的 Win10；Edge 与 Chrome 一起管。

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| W1 对账 | manifest `platforms`/`params_win`/`next_win`；`mirror_check` 命名管道 API、PowerShell 运行器、`%VAR%`、`--platform`、UTF-8 控制台；`scripts/winchecks.py` 11 个 Windows 变体 + 7 个 Windows 组件 | 通过：Win10 实机只读 exit 1 无崩溃；18 例夹具 |
| W2 渲染 | `render.py` Windows 用户 SID / 网卡别名 / `params_win`；PARAMS.txt 与 .ps1 带 BOM；用户 JSON 接受 BOM | 通过：实机渲染拿到 SID 与网卡 |
| W3 防火墙 | `system-win/firewall`（8 条规则：Anthropic v4/v6、DNS/DoT、STUN、本用户 SID 公网；先拒绝覆盖、要求服务模式与 TUN、装后验证）；`安装/卸载防火墙规则.cmd` | 脚本实机解析 0 错；**未安装** |
| W4 守护 | 计划任务 watch（命名管道查 Clash）、ipv6-guard；install/uninstall-tasks；两个 .cmd | 实机解析 0 错、渲染 0 残留；**未安装** |
| W5 浏览器/时区/体检 | Chrome/Edge `.reg`（+卸载）、`claude-wall.ps1`、install-tools、set-timezone、两个 .cmd | 实机 `.reg` 编码正确、`claude-wall.ps1 status` 只读运行 exit 6；**未安装** |
| W6 手册与 CI | `steps_win` S1–S9、`references/runbook-windows.md`、START 路线 B′、check.py Windows 校验、windows-2022 CI（Git Bash + 原生只读 smoke） | CI 多轮修 runner 差异（WSL bash、cp1252、测试平台假设） |

未做：Clash 运行时的管道 API / TUN 名 / 受管 DNS 值的观察，`dns.system` 在 Windows 为 ℹ️；全部安装器的实机安装与卸载往返；ippure。这些等用户在 Windows 机器前一次完成。

## 0.2.1 Windows 实机往返（W7，2026-10-23）

用户的 Windows 游戏机（装有 WeGame、Steam、雷神、迅游等加速器）做了一次"装 → 验 → 全撤"往返，节点用参考机同一套。

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| W7 实机修复 | 模板去掉 IP-ASN（新机器下载 ASN.mmdb 超时，整份配置验证失败）；REALITY 节点加 `support-x25519mlkem768`；住宅 socks5 `udp: false`；新组件 `clash.base_config`（Clash Verge 基础 `config.yaml` 带 dns/proxies/proxy-groups/rules 会覆盖任何订阅）；命名管道响应 chunked 解码；防火墙枚举按字符串比较；`mirror.params.json` 保留列表类型；`.cmd` 改 `-File` + 脚本自提权 + 日志（以前嵌套引号让 UAC 什么都没跑）；`一键安装全部.cmd` / `一键撤回全部.cmd`（装前快照、撤回按快照还原、读回校验）；Windows 手册加"实机踩过的坑" | 通过：一键安装 EXIT=0，Windows 全量对账 ✅23 ❌0；物理网卡直连 Anthropic 整段被墙、走 TUN 正常、局域网正常；WebRTC 与 ippure 用户口头确认通过（无截图）；一键撤回 EXIT=0，14 项与装前快照一致，TUN 关闭后直连上网正常；134 例 |

仍为 ℹ️：Windows 上 Clash Verge 2.4.4 不改系统 DNS（保持路由器地址），DNS 走向由 TUN 劫持保证。
