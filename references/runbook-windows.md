# 执行手册（Windows 10/11）：把一台 Windows 配成参考机的等价物

与 [macOS 手册](runbook.md) 同一套规矩：每步 **进入条件 → 动作 → 读什么 → 对账 → 下一步 / 停止**；对账是 `py -3 scripts\mirror_check.py --only <id>` 的输出原文；`py -3 scripts\next_step.py` 会按下面的顺序告诉你现在做哪一步。Windows 的组件 id 见附录 B（25 个），`mirror_check` 在 Windows 上自动只跑这些。

执行主体是 AI；👤 的动作由用户做（双击 `.cmd`/`.reg`、UAC 点"是"、在 Clash Verge / 设置里点、截图）。所有 `.cmd` 都把输出写到 `installers\logs\<名字>-<随机>.log`，最后一行 `EXIT=`。

## 与 macOS 的对应

| macOS | Windows | 差别 |
|---|---|---|
| PF 锚点 010/011（Claude 精确 IP / Anthropic 整段只准走 TUN） | 防火墙规则 `claude-setup-kit: net-wall v4/v6`（物理网卡出站阻断 160.79.104.0/21、2607:6bc0::/32） | Windows 不做精确 IP 更新器，只做整段 |
| PF 020（封物理 DNS/STUN；本用户公网只走 TUN） | `leak-guard dns/stun udp+tcp`（端口）+ `leak-guard user-public tcp/udp`（`-LocalUser` 本用户 SID，远端为全部公网地址） | 都只作用在物理网卡（`-InterfaceAlias`），TUN 适配器不加规则即放行；Clash 核心以服务（SYSTEM）运行所以不受 user-public 影响——**服务模式是硬前提** |
| LaunchDaemon 守护 | 计划任务 `claude-setup-kit watch`（SYSTEM，每分钟） | 只告警不重装规则（规则持久在防火墙里） |
| ipv6-guard | 计划任务 `claude-setup-kit ipv6-guard` + `Disable-NetAdapterBinding ms_tcpip6` | — |
| Chrome 描述文件 | `HKLM\SOFTWARE\Policies\Google\Chrome` 注册表（`.reg`）；Edge 同样 | 注册表策略不会被系统清掉 |
| `.command` 双击 | `.cmd` 双击 + UAC | 日志同样在 `installers\logs\` |
| `claude-wall` | `%LOCALAPPDATA%\claude-setup-kit\claude-wall.ps1` | 退出码 0/1/6 同义 |

## 推荐：一键安装 / 一键撤回（2026-10-23 实机验证）

S2–S7 可以一次做完：👤 双击 `installers\win\一键安装全部.cmd`（一次 UAC）。它先把会改动的设置（防火墙配置文件、时区、IPv6 绑定、浏览器策略键）记到 `C:\ProgramData\claude-setup-kit\before.json`，再依次装防火墙规则 → 两个计划任务 → Chrome/Edge 策略 → 体检工具 → 时区；失败即停，**再双击会跳过已装好并验证过的步骤接着装**。日志在 `installers\logs\一键安装全部-*.log`，最后一行 `EXIT=0` 才算装完。

撤回：👤 双击 `installers\win\一键撤回全部.cmd`：删规则、任务、策略值、体检工具，并照 `before.json` 把防火墙配置文件、时区、IPv6 改回去；守护历史与快照移到 `%USERPROFILE%\claude-setup-kit-uninstalled-<时间>`。Clash 的 TUN 由用户自己在 Clash Verge 里关。实机往返 14 项与安装前完全一致。

用户找不到文件时，AI 在桌面放快捷方式（PowerShell，不需要管理员）：

```powershell
$repo = "$env:USERPROFILE\claude-setup-kit"; $sh = New-Object -ComObject WScript.Shell
foreach ($n in '一键安装全部', '一键撤回全部') { $l = $sh.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\$n.lnk"); $l.TargetPath = "$repo\installers\win\$n.cmd"; $l.WorkingDirectory = "$repo\installers\win"; $l.Save() }
```

## 实机踩过的坑（2026-10-23，Win10 19045 游戏机，Clash Verge 2.4.4 / mihomo v1.19.17）

| 现象 | 原因 | 处理 |
|---|---|---|
| 导入新配置后代理页还是旧分组 | Clash Verge 的基础 `config.yaml` 被人塞了整套 dns/proxies/proxy-groups/rules，会覆盖任何订阅 | `clash.base_config` 会报；退出 Clash Verge，备份后删掉这几段 |
| 手写进 `profiles.yaml` 的配置卡能选中但不生效 | Clash Verge 不认外部注册的卡 | 一律用界面「新建 → 本地」导入 |
| 启动 90 秒后满屏报错退出，日志 `can't download ASN.mmdb` | `IP-ASN` 规则要先联网下载数据库，没代理就超时；还会留下半截坏库 | 模板已删这条；旧配置删掉它并挪走 `ASN.mmdb` |
| 丽萨（VLESS-REALITY）测速报错，其他节点正常 | 节点缺 `support-x25519mlkem768: true` | 模板已带 |
| 关了 Clash Verge 窗口再开就起不来 / 卡在验证 | 强杀 `clash-verge.exe` 会留下孤儿 `verge-mihomo.exe`；服务模式的服务也会停 | 不要强杀；必须重来时停掉全部 `clash-verge*`/`verge-mihomo` 进程，再 `Start-Service clash_verge_service`，最后让用户自己双击打开 |
| `.cmd` 里 UAC 之后什么都没执行 | 嵌套 `-Command "…\"…\"…"` 在 cmd 里被截断 | 已改为 `-File` 调脚本、脚本自提权、自写日志 |
| `reg import 'Chrome策略.reg'` 报打不开文件 | reg.exe 不认中文路径 | 一键安装直接写注册表值；单独双击 .reg 仍可用 |
| 游戏机装了雷神/迅游（WFP 驱动常驻） | 驱动在但加速器不运行时不影响 TUN 和防火墙规则 | 实验期间不开加速器；要打游戏前一键撤回、关 TUN |

## G0 约束表

同 macOS 手册 G0，外加：Clash Verge 必须用**服务模式**（否则核心以用户身份运行，会被 user-public 规则拦住）；网卡别名（`网络连接` 里显示的名字，如 `以太网` / `WLAN`）写进 `mirror.params.json` 的 `network_services`；Python 用 `py -3`（3.9+），仓库放在没有空格和中文的路径更省事（有也能跑）。

## G1 摸底（只读）

```
py -3 scripts\mirror_check.py --no-network
```
写 `mirror.params.json`（例：`{"exit_node": "<节点名>", "network_services": ["以太网"]}`），再 `py -3 scripts\render.py --component win-firewall --print-params` 核对 USER / USER_SID / WIFI_IFACE / TUN / TIMEZONE_WIN。

## S1 Clash Verge（Windows）

组件：`clash.core clash.base_config clash.mode clash.tun clash.exit clash.rules clash.google_exit clash.dns net.tun_iface dns.local53`（`dns.system` ℹ️ 只记录：实测 Clash Verge 2.4.4 Windows 开 TUN 后不改系统 DNS，网卡上仍是路由器的 DNS，真实路径由 TUN 劫持 53 保证，见 `dns.local53`）。

1. 👤 安装 Clash Verge（Windows），打开 → 设置 → **安装服务模式**（TUN 需要）。
2. AI：`py -3 scripts\render.py --component clash --nodes <节点参数.json>`（节点 JSON 放私有目录，不进仓库）。
3. 👤 配置 → 新建 → Local → 导入渲染出的 yaml；右键 → 编辑脚本 → 粘贴 `clash-profile.script.js` → 保存 → 激活；设置里开 **TUN 模式**；代理页把出口分组选到出口节点，把 `Google出口` 选成**主出口以外**的节点（Google 常把机房 IP 判成中国，Gemini 会报不支持地区）。
4. 对账：`py -3 scripts\mirror_check.py --only clash.core,clash.mode,clash.tun,clash.exit,clash.rules,clash.google_exit,clash.dns,net.tun_iface,dns.local53`。

控制通道：Windows 版 Clash Verge 在命名管道 `\\.\pipe\verge-mihomo`（`params_win.clash_api`）；若用户另设了 `external-controller`，用 `--param clash_api=http://127.0.0.1:<端口>` 并设环境变量 `MIHOMO_SECRET`。TUN 适配器默认名 `Meta`（`params_win.tun_device`）。

停止：`clash.core` ❓ = 核心没跑/管道名不同；`net.tun_iface` ❌ = TUN 没开。**S2 之前这些必须 ✅，否则防火墙规则会把本机断网**（安装器也会拒装）。

## S2 防火墙三套规则

组件：`wf.enabled wf.011 wf.020`。前置：S1；`net.tun_iface` ✅；`clash_verge_service` 在运行。
👤 双击 `installers\win\安装防火墙规则.cmd` → UAC 点"是"。读 `installers\logs\win-firewall-*.log`：`[OK] 防火墙规则已装（8 条…）`、`EXIT=0`。
对账：`--only wf.enabled,wf.011,wf.020`；再 `--only net.exit_ip,dns.upstream` 证明装墙后代理路径还通。
停止：日志里 `已存在，拒绝覆盖` → 先对账，✅ 不用装；`Clash Verge 服务模式没有在运行` / `TUN 适配器 … 不在` → 回 S1；`找不到网卡` → `mirror.params.json` 的 `network_services` 改成 `网络连接` 里的名字。

## S3 自检守护

组件：`task.watch watch.fresh`。前置：S2。
👤 双击 `installers\win\安装自检守护.cmd`。读日志 `[OK] 自检守护已装（每分钟）。最近一次：<时间>\tOK\t全部正常`。
对账：`--only task.watch,watch.fresh`。WARN 内容按对应步处理（规则缺失 → S2；TUN 不在 / 模式 / 出口 → S1）。

## S4 IPv6 守护

组件：`net.ipv6_off task.ipv6`。👤 双击 `installers\win\安装IPv6守护.cmd`。读日志 `[OK] <网卡> 的 IPv6 已解绑`。对账：`--only net.ipv6_off,task.ipv6`。

## S5 Chrome / Edge 策略

组件：`chrome.policy reg.edge`（+ 人工 `browser.webrtc`）。
👤 双击 `installers\win\Chrome策略.reg` → UAC → "是"；`Edge策略.reg` 同样。浏览器完全退出重开；打开 `chrome://policy` / `edge://policy` 截图（两条策略 来源 平台/级别 强制/状态 正常）；打开 `assets\webrtc-test.html` 截图。
对账：`--only chrome.policy,reg.edge`。没装 Chrome 时 `chrome.policy` 为 ℹ️，没装 Edge 时 `reg.edge` 为 ℹ️。撤回用 `卸载Chrome策略.reg` / `卸载Edge策略.reg`。

## S6 体检工具

组件：`tool.claude_wall_ps`。👤 双击 `installers\win\安装体检工具.cmd`（无 UAC）。日志里会直接跑一次 `status`：装齐 S2–S4 前退出码 6/1 是正常的。对账：`--only tool.claude_wall_ps`。

## S7 系统时区（语言可选）

组件：`sys.timezone`（`sys.language` ℹ️）。👤 双击 `installers\win\设置时区.cmd`（UAC；时区 id 来自 `params_win.timezone_win`，默认 `Pacific Standard Time`，`tzutil /l` 可查）。对账：`--only sys.timezone,sys.language`。

## S8 实测

`py -3 scripts\mirror_check.py --only net.exit_ip,dns.upstream`（curl.exe + nslookup，不碰 Anthropic）。WebRTC 见 S5。

## S9 交付

`py -3 scripts\mirror_check.py` 全量：`合计` 行 ❌=0 ❓=0（ℹ️ 2：语言、Windows 的系统 DNS 记录项；👉 1）。再 👤 用 Chrome/Edge 打开 <https://ippure.com/claude.html> 截两张图，按 [ippure 验收](ippure-acceptance.md) 记四项。交付内容同 macOS 手册 S12。

## 退出码

同 macOS 手册第 3 节；`.cmd` 的 `EXIT=` 来自提权后的 PowerShell：0 装好并验证；非 0 看日志里 `throw` 的那一行（`已存在，拒绝覆盖` / `服务模式没有在运行` / `TUN 适配器 … 不在` / `找不到网卡` / `装后验证失败`）。`EXIT=2` 且日志只有渲染输出 = 渲染失败，什么都没装。

## 情景推演（Windows 专有）

| 情景 | 应做 | 不能做 |
|---|---|---|
| 用户用非服务模式跑 Clash | 停在 S2 前，让用户在 Clash Verge 设置里安装服务模式 | 装 user-public 规则（会把核心也拦住） |
| `wf.enabled` ❌（Domain/Public 未启用） | 安装器会启用三个配置文件；只对账不装时提醒用户规则在那些网络类型下不生效 | 手工 `netsh` 改配置文件 |
| 网卡叫 `WLAN` 不是 `以太网` | `mirror.params.json` 写真实别名 | 改 manifest |
| 没装 Edge | `reg.edge` ℹ️，跳过 Edge策略.reg | 为了 ✅ 去装 Edge |
| 用户想自己 `reg import` | 可以，但对账要看 `chrome.policy` 的注册表值 | 接受"我改了"没有对账 |
| 弱模型把 macOS 的 `.command` 发给 Windows 用户 | 不接受：Windows 只用 `installers\win\` 下的文件 | — |
| 弱模型在 Windows 上用 `python3 scripts/...` 报错 | 改 `py -3 scripts\...` | 让用户装别的 Python |
| 控制台中文乱码 | `.cmd` 已 `chcp 65001`；脚本自己把 stdout 设为 UTF-8 | 把输出改成英文凑合 |
| `dns.system` 显示 ℹ️ | 正常：Windows 的受管 DNS 值只记录，真实路径看 `dns.local53` | 当 ❌ 去改 DNS |
| 用户这台是游戏机（LOL/PUBG、加速器） | 推荐往返：一键安装 → 对账/ippure → 一键撤回；长期只留 Clash 规则模式 + 浏览器策略 | 长期装 user-public 规则（会拦游戏和加速器的直连） |
| 用户要求在 Windows 上也做精确 IP 更新器 | 说明 Windows 侧只做整段墙 + Clash 域名规则（决定见 docs/release-tasks.md） | 移植 macOS 的更新器 |

## 附录 A：卸载

`installers\win\卸载防火墙规则.cmd`（删全部 `claude-setup-kit:` 规则）；计划任务用 PowerShell（管理员）运行 `system-win\tasks\uninstall-tasks.ps1 -Only watch|ipv6-guard|all`；`.reg` 用对应的 `卸载*策略.reg`；体检脚本删 `%LOCALAPPDATA%\claude-setup-kit\claude-wall.ps1`。卸载后对账该组件应为 ❌，这是预期。

## 附录 B：Windows 组件 → 步骤 → 安装器

| id | 步 | 安装器 / 动作 |
|---|---|---|
| `os` | G1 | — |
| `clash.core` `clash.base_config` `clash.mode` `clash.tun` `clash.exit` `clash.rules` `clash.google_exit` `clash.dns` `net.tun_iface` `dns.local53` `dns.system` | S1 | `render.py --component clash` + Clash Verge GUI（服务模式 + TUN） |
| `wf.enabled` `wf.011` `wf.020` | S2 | `一键安装全部.cmd`（S2–S7 一次装完）或 `安装防火墙规则.cmd` |
| `task.watch` `watch.fresh` | S3 | `安装自检守护.cmd` |
| `net.ipv6_off` `task.ipv6` | S4 | `安装IPv6守护.cmd` |
| `chrome.policy` `reg.edge` `browser.webrtc` | S5 | `Chrome策略.reg`、`Edge策略.reg`、`assets\webrtc-test.html` |
| `tool.claude_wall_ps` | S6 | `安装体检工具.cmd` |
| `sys.timezone` `sys.language` | S7 | `设置时区.cmd` |
| `net.exit_ip` `dns.upstream` | S8 | `mirror_check --only net.exit_ip,dns.upstream` + ippure |
| —（全部步骤） | S9 | `mirror_check` 全量 + ippure 两张截图 |
