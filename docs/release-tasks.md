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
| W13 | **Opus 复核 60 分**，两条要命的：sudoers 写的 `/usr/bin/test` 在 macOS 不存在（陌生 Mac 的 `claude-wall status` 永远退出 6、S8 ❌）；sudoers 只要留通配符就能提权（`install` 可被塞 `-m 4755`、`*` 跨参数匹配）→ 新 root 助手 `system/libexec/claude-pf-helper`（固定子命令、参数校验、零通配符），sudoers 只放行它；更新器、`claude-wall`、`mirror_check` 全部改走助手（参考机没装助手时仍走原路径）。其余：IPv6 守护属主校验对任何路径生效、日志改 `/var/log`、新 `迁移IPv6守护.command` 把旧守护换成 root 持有的；`提权对账.command` 用 `env -i` 干净环境 + `--no-network` + 保留桌面用户 UID，root 模式不执行用户脚本；sudo-only 分支不再打印"双击安装器"；跳过时标题与话术说明；`--input` 与 `--param` 同给直接报错；Windows 一键安装开头核对 UAC 账号 = 桌面用户、防火墙无法确定桌面用户就停；渲染失败任何异常都清目录；手册补提权对账/跳过 S5/迁移三种情景 | 本提交；154 例；Mac 实跑 提权对账 → `--input`；助手参数校验实测；visudo 通过；Win 154 例 OK（1 skip 为 macOS 专属）、两 ps1 解析 0 错、UAC 账号校验逻辑实机成立 |

**参考机已迁移（2026-10-23 09:56）**：用户双击 `installers/迁移IPv6守护.command`，EXIT=0，守护改为执行 root 持有的 `/usr/local/libexec/ipv6-guard.sh`，全量对账 ✅36 ❌0。这是迁移脚本的首次真机运行。
| W14 | **Opus 收尾复核 76 分**，剩余全部修：助手 `persist` 不再收任意规则文本，改为只收精确主机地址、由助手自己改写现有规则文件的 table 行（删掉 `check`）；anchor 白名单只剩本套件三个、`table-add` 的 anchor/表固定、地址只收精确主机（不收网段/主机名）、`kill` 同；`ipv6.script` 改为读 label 对应 plist 里真正执行的程序并校验属主/权限/链接与日志路径，删掉可绕过的 `ipv6_guard_script` 参数；`提权对账.command` 先以用户身份带网络跑一次、再 root 不带网络跑一次、合并（root ❓ 时取用户结果），跳过 S5 不再死循环；迁移脚本先做全部前置检查、备份到 `/var/db/ipv6-guard-migrate-*`、确认旧脚本是 IPv6 守护后才卸；锁目录 700；`/usr/local/libexec` 属主与权限校验 | 本提交；155 例；助手坏参数 16 种实测全拒；Mac 实跑合并版提权对账 → 35 ✅ ❓ 0，唯一 ❌ 为参考机旧守护（待迁移）；Win 155 例 OK |
| W15 | **Opus 终核 82 分**，3 条必修 + 零碎：助手地址校验改用 `ipaddress`（拒 `1.2.3.4.5`、`999.…`、`::`、回环/组播/链路本地）；`persist` 只增不减（旧 table 行里的地址必须都在新列表）、失败清理临时与 staging 文件；`check_daemon_program` 逐级校验上级目录属主/权限/链接、日志只允许 `/var/log` `/Library/Logs`、拒 `..`、拒 `Program`/`-c`/相对参数、plist 顶层非字典时干净 ❌；`common.sh` 新增 `assert_root_dir`，六个往 `/usr/local/libexec` 写 root 程序的安装器都在写任何东西之前校验目录链；更新器删掉无效的并发检查；提权对账打印两次各自的退出码 | 本提交；156 例；助手 11 种地址实测（坏的全拒、Anthropic 真地址与文档地址通过）；Mac 实跑合并版提权对账 35 ✅ ❓ 0 |

## 0.3.0 硬规则闸门（W16，2026-11-09）

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| W16 | 「不向 Anthropic/Claude 地址探测」从文字规则变成机器闸门：(1) `mirror_check` 运行时——`Host.run`/`Host.ps` 启动任何网络工具或 PowerShell 片段前先检查目标，命中 Anthropic/Claude 域名或 IP 段（160.79.104.0/21、2607:6bc0::/32）就抛 `ForbiddenProbe`，整轮以 2 退出，不会降级成 ❓；唯一放行的是向本机 Clash 解析器 `@127.0.0.1` 查 fake-ip；(2) `tools/check.py` 静态——扫描 64 个可执行文件，任何一行把网络工具指向这些域名就 FAIL，规则表/文档/注释不算；(3) `claude-wall` 的两处 `dig api.anthropic.com` 改为 `dig @127.0.0.1`，不再经过系统解析器 | 本提交；162 例；Mac 真机：三种禁止目标在发出请求前被拒、`calls` 为空，本机解析器查询返回 fake-ip；`claude-wall status` 照常 |

起因：2026-11-09 另一个会话在 T4 测试时经 204 匿名访问过一次 api.anthropic.com（401），违反老公的硬规则。

## 0.4.0 CDN 备用入口（W17，2026-11-09）

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| W17 | 模板加可选 `NODE4`（经 Cloudflare CDN 进 NODE1 同一台机器的 VLESS+XHTTP+TLS 备用入口：`NODE4_NAME/SERVER/PORT/UUID/HOST/PATH`），只进「出口选择」当备用成员、不进 Google 分组、不选中；新组件 `clash.xhttp_core`（配置里有 `network: xhttp` 而内核低于实测支持的 1.19.29 就 ❌ 并指向升级 Clash Verge，没有 NODE4 只记录）；`references/cdn-backup.md` 通用搭建手册（独立 xray 进程、Let's Encrypt、只放行 Cloudflare 段、优选 IP、验收表、风险；不含任何私人参数）；START 写明 NODE4 键名与两条铁规；组件数 Mac 39 / Win 28 / 共 46 | 本提交；四节点与两节点渲染都过本机 mihomo 1.19.29 `-t`；对账三态有测试；本机只读对账 ℹ️（未用 NODE4） |

**没碰的东西**：这台 Mac 与 Win 上正在运行的 Clash 配置、分组选择、规则一律未改；参考机的 CDN 节点参数未进仓库。

## 0.5.0 桌面端更新策略与 Persona 分流补齐（W18，2026-11-12）

| 卡 | 内容 | 状态 |
| --- | --- | --- |
| W18 | 配合 `claude-client-full-reset` 的更新包静态审计落地三项：(1) Clash 模板与覆写脚本补齐 `withpersona.com`、`persona.com`、`stripe.network`、`workos.com`、Statsig 伪装后缀与 `challenges.cloudflare.com`（规则 111 → 116，防止实名验证、刷卡反欺诈信标与外部登录跳转跟主会话出口不一致）；(2) 新增可选安装器 `installers/Claude禁自动更新.mobileconfig`（macOS MDM 受管 `disableAutoUpdates=true`）与 `installers/win/Claude禁自动更新.reg` / `卸载Claude禁自动更新.reg`（Windows `HKLM\SOFTWARE\Policies\Claude`）；(3) 新组件 `desktop.updater`（Mac/Win 双端，默认 `desktop_block_updates_required: false` 输出 ℹ️，识别 UTF-8 JSON 格式 `ShipItState.plist` 与挂起任务、识别 `claude_desktop_config.json` 误写，要求 AI 先调 `desktop_update_audit.py` 向用户说明**此次更新包内容 + 结合本机情况判断**后再按推荐项二选一简单询问是否开启可选禁自动更新；用户明确要锁时设 `desktop_block_updates_required: true` 才判 ✅/❌）；组件数 Mac 40 / Win 29 / 共 47 | 本提交；双端夹具测试与 Mac 真机只读对账通过，运行中的 Claude 与 ShipIt 未碰 |
| W19 | 外部用户实测反馈修复（Google 智能按需分流 + 全协议节点渲染）：(1) `clash.google_exit` 改为智能按需（默认 `google_split_required: false`）：只有主出口被 Google 误判中国（送中）且有第 2 节点时才需拆分 `Google出口`（记 ✅）；单节点或主出口未送中时支持无 `Google出口` 或与主出口共用（记 ℹ️ 放行），同时继续严格拦截 Google 走 `DIRECT` 或规则顺序错乱；(2) `render.py` 与 `clash-profile.template.yaml` 支持单节点（省略 `NODE2_*`）及任意 Clash 协议（`NODE1_TYPE`–`NODE3_TYPE` 支持 `vless`/`trojan`/`ss`/`socks5`/`vmess`/`hysteria2`/`tuic`/`anytls`，或 `NODE1_PROXY`–`NODE3_PROXY` 直接传原样节点对象），保留 Claude 主出口固定不切、禁 `DIRECT` 的硬规则 | 本提交；170 项单测与 `ruamel.yaml` 语法校验通过 |
| W20 | 防偷懒傻瓜版升级（专治外部弱模型漏项与中途停工）：(1) 新增 `scripts/auto_init.py`（自动探测当前 Clash 出口节点、物理网卡服务与旧 IPv6 守护写入 `mirror.params.json`，并自动备份补齐 `~/.claude/settings.json` 14 项官方隐私静音开关）；(2) 新增双端必查组件 `claude.privacy`（组件数 Mac 41 / Win 30 / 共 48），防止 AI 只配网络漏关后台遥测；(3) 新增 macOS `installers/一键安装全部.command` 与 `installers/一键撤回全部.command`（单次密码自动装齐 S2–S8 + 隐私开关，已装自动跳过可续跑；Windows `install-all.ps1` 同步补齐隐私开关），将 12 轮交互压缩为极简 4 步；(4) 新增 `scripts/finish_gate.py` 交卷死闸门，漏掉任何非跳过项即输出 `FINISH_GATE=BLOCKED` 拒绝交卷，全过才签发 `FINISH_GATE=PASSED` 通关核验码 | 本提交；全套单测与本机只读核验通过 |
