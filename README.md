# claude-setup-kit

把电脑配成"参考机"那样用 Claude 的**总入口**：建节点、配 Mac 环境、清理重置三件事，一个链接发给任何 AI 就能做，而且**每一步都有机器判定**（对账表、日志、退出码），能力差的模型也漏不了步。MIT 开源。

## 发给 AI 的一段话（复制粘贴即可）

> 请打开 https://github.com/qixian771-spec/claude-setup-kit ，先读 START.md（打不开 GitHub 就先让我打开现有代理再试，仍不行按 START.md 的 Download ZIP 方式做）。克隆仓库后严格按【防偷懒 4 步流程】执行，**严禁漏项、严禁中途总结收尾**：
> 1. 先运行 `python3 scripts/auto_init.py`（Windows 用 `py -3`），自动识别本机网卡/出口节点并自动补齐 Claude 14 项官方隐私静音开关；再运行 `python3 scripts/mirror_check.py` 看现状，问我要走哪条路线（建节点 / 配这台电脑 / 清理重置 / 全套从零）。
> 2. 配系统防护时优先让我双击一次 `installers/一键安装全部.command`（Windows 为 `installers\win\一键安装全部.cmd`），输一次密码装齐三道墙、守护、**双端关闭物理网卡 IPv6（含防复开守护）**与体检工具，不要拆成十几轮折腾我；其余每轮运行 `python3 scripts/next_step.py`，按 references/conversation.md 的大白话告诉我点哪里。
> 3. 硬规则：出口节点不许切换、不许退出 Clash、不许向 Anthropic 地址直连试探；要密码的动作由我双击完成，你只读日志和对账。
> 4. **交卷死闸门**：最后你必须运行 `python3 scripts/finish_gate.py`，在它打出 `FINISH_GATE=PASSED` 通关核验码并贴出原文之前，绝对不准说“配好了”；拿到核验码后再按 references/ippure-acceptance.md 让我截图验收。

## 它由三部分组成

| 部分 | 仓库 | 管什么 |
|---|---|---|
| 总入口 + 双端环境镜像 | **本仓库** | `START.md` 防偷懒 4 步总流程；`auto_init.py` 自动认路与 14 项隐私静音开关补齐；`manifest.json` 48 个组件（Mac 41、Windows 30）；Mac/Windows 双端 `一键安装全部` 与 `一键撤回全部`；`mirror_check.py` 只读对账；`next_step.py` 下一步导航；`finish_gate.py` 交卷死闸门；ippure 验收 |
| 建节点 | [vps-node-rebuild-3xui](https://github.com/qixian771-spec/vps-node-rebuild-3xui) | VPS、3x-ui、VLESS-REALITY 节点部署与验收 |
| 清理重置 | [claude-client-full-reset](https://github.com/qixian771-spec/claude-client-full-reset) | Claude 本地数据与标识清理、清理前后 ID 快照对比、遥测开关与分流补齐、桌面端暂存更新包只读拆检（`desktop_update_audit.py`） |

START.md 会在需要时让 AI 克隆另外两个仓库并按它们的手册走；用户不需要再分别发链接。

## 本仓库的工具

| 东西 | 作用 |
|---|---|
| `START.md` | AI 的防偷懒总手册：极简 4 步流水线、四条路线、交卷死闸门 |
| `scripts/auto_init.py` | 零门槛自动初始化：自动探测当前 Clash 出口节点、物理网卡与旧守护，并备份补齐 `~/.claude/settings.json` 的 14 项官方隐私静音开关 |
| `manifest.json` | 48 个组件（Mac 41 / Windows 30）的契约（怎么验证、失败下一步）+ 步骤顺序、前置、安装器、对用户说的话 |
| `scripts/mirror_check.py` | 一条命令只读对账，✅/❌/❓/ℹ️/👉 表与退出码 0/1/2 |
| `scripts/next_step.py` | 读对账结果，按步骤顺序打印"现在做什么"；全过时指引跑交卷闸门与 ippure 验收 |
| `scripts/finish_gate.py` | **防偷懒交卷死闸门**：漏掉任何一项即打印 `FINISH_GATE=BLOCKED` 拒绝交卷；全过才签发 `FINISH_GATE=PASSED` 通关核验码 |
| `scripts/render.py` | 把 `system/`、`templates/` 的占位符模板按本机参数渲染到独立目录（支持单节点与任意 Clash 协议） |
| `scripts/ios_render.py` | 一键把本机 Clash 或节点 JSON 转成 iPhone / iPad 配置：V2Box（JSON + 链接）、小火箭（`.conf`）、Stash / Karing（YAML），对齐同出口、关 IPv6、拦 STUN 与 116 规则 |
| `templates/clash-profile.template.yaml` | 参考机的 Clash 配置（116 条规则，含 Persona 实名、Stripe Radar 刷卡信标、WorkOS 登录与 Statsig 伪装后缀固定走 Claude 出口，去掉了新机器会卡死的 IP-ASN）：Claude 固定出口分组（支持单节点及 VLESS/Trojan/SS/SOCKS5 等任意 Clash 协议）+ 智能按需的 Google 专用分组（仅在主出口被 Google 误判中国时启用 NODE2）+ 遥测/CDN/第三方规则；NODE2、NODE3、NODE4（Cloudflare CDN 备用入口，XHTTP）均可选 |
| `installers/一键安装全部.command`、`一键撤回全部.command` | **Mac 省事首选**：双击 1 次、输 1 次密码装齐三道墙 + 更新器 + 自检守护 + IPv6 守护 + 体检工具 + 隐私静音开关（Windows 对应 `installers\win\一键安装全部.cmd` / `一键撤回全部.cmd`）；也保留单步 `安装*.command` / `卸载.command` |
| `installers/Chrome策略.mobileconfig`、`Claude禁自动更新.mobileconfig` | Chrome WebRTC/DoH 策略描述文件；Claude Desktop 可选禁自动更新受管策略（Windows 对应 `Claude禁自动更新.reg`，必须询问用户，默认不装） |
| `assets/webrtc-test.html` | 本地 WebRTC 候选检查 |
| `tools/check.py`、`tools/redact_check.py` | 打包检查；脱敏扫描（公网 IP、UUID、凭据、私人路径 0 命中才能提交） |
| [references/runbook.md](references/runbook.md) / [runbook-windows.md](references/runbook-windows.md) | Mac 路线 S1–S12、Windows 路线 S1–S9 的逐步手册与情景推演 |
| [references/runbook-ios.md](references/runbook-ios.md) | iPhone / iPad 路线 E 部署手册（国行防漏地区/定位规矩、V2Box 直接扫码 / 小火箭 / Stash / Karing 导入、Safari 网页与原生 App 指引） |
| [references/cdn-backup.md](references/cdn-backup.md) | 给自己的节点加一个经 Cloudflare CDN 的备用入口（VLESS+XHTTP+TLS，独立 xray 进程、Let's Encrypt、只放行 Cloudflare 段），对应模板里可选的 NODE4 |
| [references/ippure-acceptance.md](references/ippure-acceptance.md) | 最终以 <https://ippure.com/claude.html> 四项为验收 |

## 快速验证

macOS，系统自带 Python 3（3.9 起，无第三方依赖）：

```sh
python3 scripts/mirror_check.py && python3 scripts/next_step.py
```

```sh
python3 -m unittest discover -s tests && python3 tools/check.py && python3 tools/redact_check.py
```

本机参数放在仓库根目录的 `mirror.params.json`（git 忽略），例如 `{"exit_node": "你的节点名"}`。节点密钥只通过 `render.py --nodes <文件>` 传入，不进仓库。

## 边界

不改硬件指纹、不保证账号不被风控；Windows 10/11 走 [Windows 手册](references/runbook-windows.md)（防火墙规则 + 计划任务 + 注册表策略，不做精确 IP 更新器）；Firefox 没有策略模板（只有 PF UID 规则兜底）；Claude 走共用 CDN 的域名靠 Clash 规则而不是 PF。每一步做不到的事都要在交付里写明。
