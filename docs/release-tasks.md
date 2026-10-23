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

## 0.2.2 陌生人演练（W8–W9，2026-10-23）

做法：从 GitHub 干净克隆到临时目录，在 Mac（参考机）和 Windows 游戏机上只跑陌生人会跑的命令；再派一个弱模型（Haiku）扮演"收到链接的 AI"只读走 START.md，报回卡点。

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| W8 | 国内无代理连不上 GitHub（Win 关 TUN 后 clone 两次被重置、curl 15 秒超时）→ README 粘贴段、START 第 0 步、Windows 手册写明先开 Clash 系统代理 / 用别的设备 Download ZIP；Windows 网卡别名不存在时 `dns.system`/`net.ipv6_off` 直接列出现有网卡并指向 `mirror.params.json`（原来是一段 CIM 错误）；`check.py`/测试在 Windows 找 Git 自带的 bash（Git 不在 PATH 也找 Program Files，绝不用 System32 的 WSL 启动器），没有 Git Bash 时明说 SKIPPED；`dns.system` 文案改为实测结论 | 通过：`b8e2fac` run 39972813048 四 job success；Win 实跑三种 PATH 情况 136 例 OK |
| W9 | Haiku 第一轮演练 64 分，核实后 14 条真问题：文档组件数 36/25 过期（实际 Mac 38 / Win 27 / 共 45）；对话模板写死项数；`mirror_check` 无参数文件时首行不提醒；START 没写 `next_step` 退出码 3 的含义、Windows 前置 Git/Python、`network_services`；steps_win S2 话术指向旧安装器；S7 话术两处不一致；✅ 证据不解释 114 DNS 与 updater 退出码 1；`render.py` 说明只写 Mac；一键装后 S3–S7 的关系、游戏机最终状态、claude-wall.ps1 执行策略、ALTQ 过滤未说明 | 通过：`cafccdc` run 39974014029 四 job success；137 例 |
| W10 | Haiku 第二轮演练 58 分，核实后 13 条真问题。硬伤三条：Windows 一键安装改时区没征得同意 → START 必问时区、S2 话术列出一键会做的全部事、手册先问再双击；steps_win 的 `log` 字段（win-watch 等）与 .cmd 实际日志名不符 → 改成文件名并加测试；Mac `uninstall-ipv6-guard.sh` 不管 label 是否是自己装的都删脚本 → 没有自己 label 的 plist 就 EXIT=73 拒卸。其余：`next_step` 全过分支与日志路径按平台输出、`--platform` 同时决定打印的命令；`合计` 行加「共 N 项」；START 写明 mirror_check 的探测目标与 `sudo -n`、`ipv6_guard_label` 怎么发现、节点键名按协议、Windows 还要装 Clash Verge 服务模式、AGENTS.md 与本仓库规则的优先级；对话模板加 Windows 说明与 👤/👉 对应；EXIT=72 的处理三处统一为"对账，❌ 停下报告，AI 不自己卸" | 本提交；139 例 |
| W11 | Haiku 第三轮演练 55 分，核实后 20 条真问题。阻断：模板无条件要求 NODE3（socks5），只有两个节点的人渲染直接失败 → `render.py` 支持 `# {{IF KEY}}…# {{ENDIF}}` 块与行尾 `# {{IF KEY}}` 条件，NODE3 可选（两节点渲染过 mihomo `-t`）。其余：`clash.base_config` 修法与"不退出 Clash"硬规则的关系写明（S1 配置阶段唯一例外）；脚本"可选"三处统一；manifest 两处指向不存在的 `clash-verge.template.yaml`；Chrome 描述文件路径统一；S1 user_action 补系统代理开 / DNS 覆写关 / Google出口；对话模板改为先问节点名再对账；`daemon.ipv6` 的 next 先找已有守护；EXIT=73 一词多义写明；S8 依赖补 S6；claude-wall 找不到命令的全路径；Windows：用户目录安装的 Chrome/Edge 也能查到、防火墙装一半后一键续跑的处理、.reg 单独双击标为未实测、双管理员账号 SID 的已知限制、S2 话术写明三个防火墙配置文件都会打开；sudo 提示带 `--only <id>`；START 补本机 DNS 探测说明 | 本提交；142 例 |
| W12 | **Opus 深度审计 50 分**，所找全部修：（阻断）无免密 sudo 的新 Mac 卡死在 S2/S9 → 新 `installers/提权对账.command`（用户双击、只读、写 `installers/logs/mirror-sudo-latest.json`），`next_step` 遇到"全是 sudo ❓"时改指向它并用 `--input` 续走，sudoers 加 `profiles -P`；用户拒绝某步后流程走不完 → `skip_steps` 参数，跳过并级联、最后列出；（安全）IPv6 守护以 root 跑用户可写脚本 → 搬到 `/usr/local/libexec/ipv6-guard.sh` root 持有，`ipv6.script` 校验属主；sudoers 的 `*` 可匹配 `/`、`awk *` 可 root 执行任意程序 → 全部钉死路径、claude-wall 改 `cat | awk`；（会做错）next_step 不打印组件 next；撤回措辞；Windows 提权后渲染的 SID → install-firewall 比对桌面用户 SID；Mac 用户目录 Chrome；时区按精确列表（东京/新加坡可用）；EXIT=73 文案与装载器退出码映射 74；卸 IPv6 守护只删 plist 指向本套件脚本的；Mac network_services 发现法；杀 Clash 进程改为用户自做；（会卡住）Mac 前置 xcode-select/Clash Verge 服务模式；ZIP 路线另两仓库与 Gatekeeper；节点协议写死说明；Windows 命令改正斜杠；base_config 例外进硬规则；卸更新器挪状态目录；`ipv6_guard_script` 参数；渲染失败清理空目录；文案 6 处 | 本提交；149 例；Mac 实跑 提权对账.command → `--input` 全过；Win 实跑 149 例 OK、SID 逻辑成立 |
