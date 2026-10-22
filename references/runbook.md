# 执行手册：把一台 Mac 配成参考机

流程主入口。每一步的格式固定：**进入条件 → 动作 → 读什么 → 对账 → 下一步 / 停止**。对账永远是 `python3 scripts/mirror_check.py --only <id>` 的输出原文；没贴输出的步骤等于没做。组件 id 见 [manifest.json](../manifest.json)，全部 36 个在附录 B 对照表里。

执行主体是 AI；只有标了 👤 的动作要用户亲自做（双击 `.command`、输密码、在 Clash Verge / 系统设置里点按钮、截图）。AI 渲染、读日志、对账、交付。

## G0 接收任务 → 约束表

进入：收到"把这台 Mac 配成和参考机一样 / 按清单检查"的请求。

填好再动手（缺的问一次，已给的不再问）：

| 项 | 来源 | 缺失时 |
|---|---|---|
| 节点来源 | 用户已有节点（订阅或自建；自建见 vps 仓库） | 停止：本仓库不建节点 |
| 出口分组名、出口节点名 | 用户说；默认 manifest `exit_group`=出口选择、`exit_node` 由用户定 | 停止：没有节点名就没法对账 `clash.exit` |
| 网络服务名 | `networksetup -listallnetworkservices`，一般 `Wi-Fi` | 用 `--param network_services=<名>` |
| 已装过什么 | G1 的对账表 | — |
| 授权 | 用户同意装 PF 规则、LaunchDaemon、sudoers 最小规则、描述文件；同意 IPv6 关闭 | 未授权的组件跳过并在交付里列出 |
| 硬约束 | 出口固定不切；不碰 Anthropic 地址；正在用 Claude 时不重载 Clash | 始终 |

## G1 摸底（只读）

进入：G0 完成。

动作：
1. `python3 scripts/mirror_check.py --json > <私有目录>/mirror-before.json`，再 `python3 scripts/mirror_check.py` 看表。
2. 本机参数写进仓库根的 `mirror.params.json`（git 忽略）：至少 `exit_node`；参考机还用 `ipv6_guard_label`。例：
   ```json
   {"exit_node": "<节点名>"}
   ```
3. `python3 scripts/render.py --component watch --print-params` 核对 USER/HOME/UID/TUN/EXIT_*/WIFI_* 全部正确。

读：对账表。❓ 大多是"需要 sudo"——这台机器如果 `sudo -n` 不免密，PF 相关项要用 `sudo python3 scripts/mirror_check.py --only pf.enabled,pf.010,pf.011,pf.020,watch.fresh` 再看一次（只读）。

通过：知道哪些 id 是 ❌/❓，形成本次要做的步骤子集。下一步 S1（若 `clash.*` 全 ✅ 则从第一个 ❌ 的步开始）。

## S1 Clash Verge

进入：G1 完成；用户有节点参数。组件：`clash.core clash.mode clash.tun clash.exit clash.rules clash.dns net.tun_iface dns.local53 dns.system`。

动作：
1. 👤 安装 Clash Verge（参考机 2.5.2，核心 mihomo v1.19.29），打开一次，**设置 → 服务模式 安装**（TUN 需要）。
2. AI 把节点参数写成 JSON（键名见 `templates/clash-profile.template.yaml` 里的 `{{NODEn_*}}`；文件放私有目录，**不进仓库**），渲染：
   `python3 scripts/render.py --component clash --nodes <节点参数.json>` → 输出目录里 `templates/clash-profile.template.yaml` 与 `clash-profile.script.js`。
3. 👤 Clash Verge → 配置 → 新建 → 类型 Local → 导入渲染出的 yaml；右键该配置 → 编辑脚本 → 粘贴 `clash-profile.script.js` 内容 → 保存；激活该配置。
4. 👤 设置：开 TUN 模式、系统代理开、DNS 覆写关（脚本已写 DNS）；代理页把 `出口选择` 选到出口节点。
5. 对账：`python3 scripts/mirror_check.py --only clash.core,clash.mode,clash.tun,clash.exit,clash.rules,clash.dns,net.tun_iface,dns.local53,dns.system`

读：九项全 ✅。`dns.system` 显示 114.114.114.114 是 Clash Verge 自己写的，接受；真正的路径由 `dns.local53` 证明。

停止：`clash.core` ❓ = 核心没起/控制 socket 路径不同（`--param clash_api=`）；`clash.exit` ❌ = 分组里有 DIRECT 或没选到节点，先在 GUI 改；`clash.rules`/`clash.dns` ❌ = 导入的不是渲染文件或脚本没绑定。不进 S4 之前这些必须 ✅——**S4 的墙会把没走 TUN 的公网全部拦掉**。

## S2 Claude 直连墙（010）

进入：S1 通过。组件：`pf.enabled pf.010 loader.010 daemon.010 pf.conf`。

动作：👤 双击 `installers/安装Claude直连墙.command` → Terminal 里输入开机密码 → 等"安装结束"。
读：`installers/logs/direct-wall-<时间>.log` 最后一行 `EXIT=0`，上面有 `[OK] Claude 直连墙（锚点 010）已装载` 和目标表两条地址。
对账：`--only pf.enabled,pf.010,loader.010,daemon.010,pf.conf`（PF 项如需 sudo 见 G1）。
停止：`EXIT=72` 已存在（先卸载再装，附录 A）；`EXIT=73` pf.conf 语法失败已自动恢复备份——把日志贴给用户，不要手改 pf.conf。

## S3 Anthropic 整段墙（011）

进入：S2 通过。组件：`pf.011 loader.011 daemon.011`。
动作：👤 双击 `installers/安装Anthropic整段墙.command`。读 `installers/logs/net-wall-*.log`，`[OK] … 名单：` 下应有 `160.79.104.0/21` 与 `2607:6bc0::/32`。
对账：`--only pf.011,loader.011,daemon.011`。

## S4 防泄露墙（020）

进入：S1–S3 通过，且此刻 `net.tun_iface` ✅（安装器自己也会查，TUN 不在直接拒装）。组件：`pf.020 loader.020 daemon.020 pf.conf`。

对用户先说清楚：装上后这个用户的公网新连接只能走 TUN；Clash 一停整台机器断公网，这是设计。
动作：👤 双击 `installers/安装防泄露墙.command`。读 `installers/logs/leak-guard-*.log`：`[OK] 防泄露墙（锚点 020）已装载：… UID <uid> 的公网只准走 <tun>`。
对账：`--only pf.020,loader.020,daemon.020,pf.conf`；再跑一次 `--only net.exit_ip,dns.upstream` 证明装墙后代理路径还通。
停止：`EXIT=75` TUN 不在 → 回 S1；`EXIT=65` UID 不对 → 参数渲染错了，`render.py --print-params` 重新核对。

## S5 地址更新器

进入：S2 通过。组件：`daemon.updater updater.fresh`。

动作：👤 双击 `installers/安装地址更新器.command`。它会装最小 sudoers 规则（`/etc/sudoers.d/claude-mac-env-mirror`，先 `visudo -cf`）、包目录、用户状态目录、LaunchDaemon，并等 15 秒看首轮结果。
读：日志 `[OK] 地址更新器已装（每 15 分钟）。首轮结果：{"status": "APPLIED"…` 或 `STOPPED_OLD_TARGETS_NOT_REMOVED`（保守停止也算装好了）。
对账：`--only daemon.updater,updater.fresh`。`updater.fresh` 要有 6 小时内的 APPLIED；首轮就是 STOPPED 的话等下一轮（15 分钟）再对账一次。

## S6 自检守护

进入：S2–S4 通过（守护要用三个装载器）。组件：`loader.watch daemon.watch watch.fresh`。
动作：👤 双击 `installers/安装自检守护.command`。读日志 `[OK] 自检守护已装。最近一次：<时间>\tOK\t全部正常`。
对账：`--only loader.watch,daemon.watch,watch.fresh`。
读到 WARN 不是安装失败：看 WARN 内容（Clash 不是 rule 模式 / 出口不是预期 / 更新器超 6 小时），回对应的步处理。

## S7 IPv6 守护

进入：G0 已授权关 IPv6。组件：`net.ipv6_off daemon.ipv6 ipv6.script`。
动作：👤 双击 `installers/安装IPv6守护.command`。读日志 `[OK] Wi-Fi 的 IPv6 已关，守护 <label> 每 30 秒复查`。
对账：`--only net.ipv6_off,daemon.ipv6,ipv6.script`。
`daemon.ipv6` 的 label 来自参数 `ipv6_guard_label`（默认 `local.ipv6-guard`）；对账用的是同一个参数，不要在 manifest 里硬改。

## S8 体检工具

进入：S5 通过（它的 `sudo -n` 用的是更新器那条 sudoers 规则）。组件：`tool.claude_wall`。
动作：👤 双击 `installers/安装体检工具.command`（不要 root）。读日志最后 `[OK] claude-wall 已装到 ~/.local/bin`，上面有 `PF: 已启用…`、`DNS: fake-ip 正常`、`守护: 正常`。
对账：`--only tool.claude_wall`。

## S9 Chrome 描述文件

进入：Chrome 已安装（`chrome.policy` 为 ℹ️ 表示没装 Chrome，跳过本步）。组件：`chrome.policy browser.webrtc`。

动作：
1. 👤 双击 `installers/Chrome策略.mobileconfig` → macOS 提示"已下载描述文件" → 系统设置 → 通用 → 设备管理 → 选中"Claude 环境镜像：Chrome 防泄露策略" → 安装 → 密码。
2. 对账：`--only chrome.policy`（要同时看到 Managed Preferences 文件和已安装描述文件）。
3. 👤 Chrome ⌘Q 完全退出再打开；打开 `chrome://policy`，截图：`DnsOverHttpsMode=off`、`WebRtcIPHandling=disable_non_proxied_udp`，来源 平台、级别 强制、状态 正常。
4. 👤 用 Chrome 打开 `assets/webrtc-test.html`（可填预期出口 IP），截图 ✅。

停止：手工把 plist 写进 `/Library/Managed Preferences` 不算——没有描述文件支撑会被系统清掉（参考机 10 月 12 日就是这样丢的）。

## S10 系统设置

组件：`sys.timezone`（必做）、`sys.language`（可选，ℹ️）。
动作：👤 系统设置 → 通用 → 日期与时间 → 关自动 → 选节点所在时区。语言顺序按 [ippure 验收](ippure-acceptance.md) 的说明由用户决定。
对账：`--only sys.timezone,sys.language`。

## S11 实测

进入：S1–S10 中本次要做的都 ✅。组件：`net.exit_ip dns.upstream browser.webrtc`。
动作：`python3 scripts/mirror_check.py --only net.exit_ip,dns.upstream`（经代理访问 Cloudflare trace 与 whoami，不碰 Anthropic）；WebRTC 见 S9 第 4 条（Safari 也测一次）。
然后 👤 用 Chrome 打开 <https://ippure.com/claude.html>，整页截两张（上半、分数区），按 [ippure 验收](ippure-acceptance.md) 记四项。

## S12 交付

动作：`python3 scripts/mirror_check.py` 全量，`合计` 行 ❌=0、❓=0（ℹ️ 1 语言、👉 1 WebRTC 人工项是正常的）。
交付内容：全量对账表原文 + 每步日志路径 + chrome://policy 截图 + WebRTC 截图 + ippure 两张截图 + 没做/做不到的项（未授权跳过的、Firefox、硬件指纹、Claude 共用 CDN 域名）。

## 3. 退出码

| 命令 | 0 | 1 | 2 | 其他 |
|---|---|---|---|---|
| `mirror_check.py` | 全部 ✅（ℹ️/👉 不计） | 有 ❌ | 有 ❓（要 sudo / 工具缺 / 网络不可达 / `--no-network`） | — |
| `render.py` | 渲染完成，首行是输出目录 | — | 参数或占位符错误（stderr `[ERROR]`） | — |
| `installers/lib/install-*.sh` | 装好并验证 | — | — | 64 用法 · 65 参数不对 · 70 不是 root · 71 缺渲染文件 · 72 已存在拒绝覆盖 · 73 前置缺失/pf.conf 语法 · 74 装后验证失败 · 75 TUN 不在 |
| `.command` 日志 `EXIT=` | 同上 | | | 2 = 渲染失败，什么都没装 |

`[OK]` 出现过不代表后面没失败，看最后的 `EXIT=`。

## 4. 情景推演（文档推演，不是演示指令）

| 输入情景 | 应做 | 明确不能做 |
|---|---|---|
| 用户只问"我这台差什么" | G1 对账表，报告，结束 | 顺手装任何东西 |
| 用户没有节点 | 停在 G0，指向 vps 仓库 | 用公共免费节点凑数 |
| `clash.exit` 显示分组里有 DIRECT | 让用户在 GUI 删掉 DIRECT 再对账 | 改 manifest 把 DIRECT 放行 |
| `dns.system` 是 114.114.114.114 | 看 `dns.local53`，✅ 就接受 | 去把系统 DNS 改成 1.1.1.1 |
| 装 020 时 `EXIT=75` | 回 S1 把 TUN 开起来 | 改脚本跳过检查 |
| 装 010 时 `EXIT=73` | 把日志贴出来，pf.conf 已自动恢复 | 手改 /etc/pf.conf |
| `EXIT=72` 已存在 | 先对账该组件，✅ 就不用装；❌ 才卸载重装 | 直接覆盖 |
| `watch.fresh` 是 WARN "出口选择不是 X" | 对照用户要的节点名改 `mirror.params.json`，或让用户在 GUI 选回 | 为了让它 OK 去切节点 |
| `updater.fresh` ❌ 首轮 STOPPED | 等 15 分钟再对账；连续 6 小时 STOPPED 才算问题 | 删除旧目标表 |
| `chrome.policy` ❌ 但 ippure WebRTC 显示未泄露 | 仍要装描述文件（现在只靠 PF 兜底） | 宣称 WebRTC 已处理 |
| 用户说"我把 plist 直接放进 Managed Preferences 了" | 说明会被清掉，走描述文件 | 接受 |
| 弱模型跳过了 S11 直接写"全部完成" | 不接受：没有 `net.exit_ip`/`dns.upstream` 输出与 ippure 截图 | — |
| 弱模型用自己的内置浏览器做 ippure | 不接受：不是用户的 Chrome，没有策略 | — |
| 弱模型只贴了 `[OK]` 没贴 `EXIT=` | 让它贴整份日志尾部 | — |
| 用户正在用 Claude 时要重载 Clash | 推迟到用户不用时；或只做不需要重载的步 | 让 Clash 重新激活 |
| `mirror_check` 全 ❓ | `sudo -n` 不免密，按 G1 用 sudo 跑 PF 项 | 把 ❓ 当 ✅ |
| 另一台 Mac 的网络服务叫 "Wi‑Fi 2" | `--param network_services=Wi‑Fi 2`，并写进 `mirror.params.json` | 改 manifest |
| 用户要求也配 Firefox | 说明不在覆盖范围（无策略模板），只有 PF UID 规则兜底 | 编一套没验证过的 Firefox 配置 |
| 用户让 AI 自己 `sudo` 装 | 说明安装只走双击文件，AI 读日志 | 自己提权 |
| 用户让测"出口断了会不会直连" | 解释 020 + 010/011 的 fail-closed 设计（不会直连），不做断网测试 | 退出 Clash 试 |
| 语言顺序 zh 第一 | ℹ️ 记录 +24 分，问用户要不要改 | 擅自改系统语言 |
| 共用 CDN（downloads.claude.ai、statsig）走不了墙 | 交付里写明：这些靠 Clash 规则，不靠 PF | 把 Google/CloudFront 整段写进墙 |

## 附录 A：卸载与回滚

👤 双击 `installers/卸载.command`，输入组件名。顺序建议：updater → watch → leak-guard → net-wall → direct-wall；ipv6-guard、claude-wall 独立。每个卸载脚本只删自己装的文件，`pf.conf` 的装载行去掉前先备份并做语法检查；`/var/db/*` 的历史与用户目录下的日志保留。卸载后对账该组件应为 ❌（文件不存在），这是预期。

## 附录 B：组件 → 步骤 → 安装器 对照

| id | 步 | 安装器 / 动作 |
|---|---|---|
| `os` | G1 | — |
| `clash.core` `clash.mode` `clash.tun` `clash.exit` `clash.rules` `clash.dns` `net.tun_iface` `dns.local53` `dns.system` | S1 | `render.py --component clash` + Clash Verge GUI |
| `pf.enabled` `pf.010` `loader.010` `daemon.010` `pf.conf` | S2 | `安装Claude直连墙.command` |
| `pf.011` `loader.011` `daemon.011` | S3 | `安装Anthropic整段墙.command` |
| `pf.020` `loader.020` `daemon.020` | S4 | `安装防泄露墙.command` |
| `daemon.updater` `updater.fresh` | S5 | `安装地址更新器.command` |
| `loader.watch` `daemon.watch` `watch.fresh` | S6 | `安装自检守护.command` |
| `net.ipv6_off` `daemon.ipv6` `ipv6.script` | S7 | `安装IPv6守护.command` |
| `tool.claude_wall` | S8 | `安装体检工具.command` |
| `chrome.policy` `browser.webrtc` | S9 | `Chrome策略.mobileconfig` + `assets/webrtc-test.html` |
| `sys.timezone` `sys.language` | S10 | 系统设置（用户） |
| `net.exit_ip` `dns.upstream` | S11 | `mirror_check --only net.exit_ip,dns.upstream` + ippure |
| —（全部步骤） | S12 | `mirror_check` 全量 ❌=0 ❓=0 + ippure 两张截图 |
