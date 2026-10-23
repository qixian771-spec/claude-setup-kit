---
name: claude-setup-kit
description: 在 macOS 上把 Claude 的本机网络与浏览器环境照参考机原样复制并逐项对账：Clash Verge 固定出口与 fake-ip DNS、PF 三道墙（Claude 精确 IP、Anthropic 整段、物理 DNS/STUN 与本用户公网只走 TUN）、自检守护、地址更新器、IPv6 守护、Chrome WebRTC/DoH 描述文件、时区；只读对账命令 mirror_check 给出每项 ✅/❌ 与下一步，安装靠用户双击，最终以 ippure.com/claude.html 四项为验收。不建节点、不清理账号数据（见另两个仓库）。
license: MIT
---

# Claude 环境总入口与 Mac 环境镜像

用户只发这一个仓库的链接。**先读 [START.md](START.md)**：它让你问用户要走哪条路线（A 建节点 → 克隆 vps 仓库；B 配 Mac → 本仓库；C 清理重置 → 克隆 reset 仓库；D 全套），并规定各路线的产出与交回。本页其余部分是 B 路线（把一台 Mac 配成和参考机一样）的入口：清单是 [manifest.json](manifest.json)（Mac 38 个组件、12 个步骤；Windows 27 个组件、9 个步骤），对账命令是 `python3 scripts/mirror_check.py`，`python3 scripts/next_step.py` 会告诉你现在该做哪一步；它们的输出是唯一算数的证据，**不靠 AI 自己说"做好了"**。

## 三个仓库分工（别混）

| 仓库 | 管什么 | 什么时候用 |
|---|---|---|
| [vps-node-rebuild-3xui](https://github.com/qixian771-spec/vps-node-rebuild-3xui) | 服务器端：建 VPS、3x-ui、出节点 | 还没有节点 |
| **claude-setup-kit**（本仓库） | 本机端：Clash 配置、防火墙、守护、浏览器策略、系统设置、ippure 验收 | 有节点了，要把 Mac 配成参考机那样 |
| [claude-client-full-reset](https://github.com/qixian771-spec/claude-client-full-reset) | 清理重置：Claude 本地数据、标识、遥测与分流补齐 | 换账号、封号后清理、补遥测开关 |

## 必须先读与执行顺序

**先读 [执行手册](references/runbook.md)**。它把 Mac 的 38 个组件排成 12 步，每步固定为：进入条件 → 动作（命令或让用户双击哪个文件）→ 读哪份日志 → 贴 `mirror_check --only <id>` 的输出 → 才能进下一步。带不懂技术的用户时，按 [对话模板](references/conversation.md) 说话和停顿。最后按 [ippure 验收](references/ippure-acceptance.md) 做四项检测。

1. 按 START.md 问路线；提取节点来源、出口分组与节点名、已有授权；沿用已给信息，不重复问。
2. 先跑一次 `python3 scripts/mirror_check.py`（只读，不需要 sudo 也能跑大部分项），拿到现状表再决定做哪些步。
3. 把本机参数写进 `mirror.params.json`（出口节点名、ipv6 守护 label 等；见手册 G1），不要改 manifest.json。
4. 每一轮跑 `python3 scripts/next_step.py`，照它打印的做；**每一步只做那一步的组件**，日志退出码不是 0 就停下报告。
5. 全部 ✅（ℹ️ 和 👉 除外）后做 ippure 验收，截图与 `mirror_check` 全量输出一起交付。

## 入口与按需阅读

| 用户目标 | 入口 | 读 |
|---|---|---|
| 不知道用户要什么 / 刚拿到链接 | 读 [START.md](START.md)，问路线 | [START.md](START.md) |
| 看看这台机器现在差什么 | `python3 scripts/mirror_check.py`（`--json` 给 AI 解析；`--only id,id` 单项） | [手册 G1](references/runbook.md#g1-摸底只读) |
| 现在该做哪一步 | `python3 scripts/next_step.py`（退出 3 = 打印了待做步；0 = 全过，去 ippure） | [手册](references/runbook.md) 对应步 |
| 从零配到和参考机一样 | 手册 S1–S12 顺序执行（Windows：S1–S9） | [执行手册](references/runbook.md) / [Windows 手册](references/runbook-windows.md) |
| 只装某一个组件 | `installers/安装<组件>.command`（用户双击）→ 读 `installers/logs/` | [手册 S2–S9](references/runbook.md#s2-claude-直连墙010) |
| 把 Clash 配置做成和参考机一样 | `python3 scripts/render.py --component clash --nodes <节点参数.json>` → 导入 Clash Verge | [手册 S1](references/runbook.md#s1-clash-verge) |
| 卸掉某个组件 | `installers/卸载.command`（用户双击，输入组件名） | [手册附录 A](references/runbook.md#附录-a卸载与回滚) |
| WebRTC / DNS / 出口实测 | `assets/webrtc-test.html` + `mirror_check --only net.exit_ip,dns.upstream` + ippure | [ippure 验收](references/ippure-acceptance.md) |
| 在仓库里改东西 | `python3 tools/check.py` + `python3 -m unittest discover -s tests` + `python3 tools/redact_check.py` | [docs/release-tasks.md](docs/release-tasks.md) |

## 不可放宽的规则

- **出口固定**：永远不为了测试切换出口节点、退出 Clash 或关 TUN；需要这类操作的验证一律标"未验证"。
- **不碰 Anthropic 地址**：出口与 DNS 实测只用公开第三方端点（Cloudflare trace、whoami 查询、ippure 页面），不 curl claude.ai / anthropic.com。
- **装东西靠用户双击**：所有写 `/etc`、`/Library`、`/usr/local`、sudoers 的动作都在 `installers/*.command` 里，AI 只渲染、只读日志、只对账；不替用户输密码，不自己 `sudo`。
- **没有兜底**：安装器遇到"已存在"就拒绝，遇到 TUN 不在就拒装防泄露墙，`pf.conf` 语法不过就恢复备份并停止；AI 不得改脚本让它"过"。
- **证据只认 mirror_check 与日志**：每一步的验收是那一步对应 id 的 ✅ 行原文；"应该可以"不算。做不到的事（硬件指纹、共用 CDN 的 Claude 下载域名、节点本身的健康）在交付里写明。
- **仓库里不放任何真实节点、密钥、私人路径**：提交前 `python3 tools/redact_check.py` 必须 0 命中。

## 能做与不能做

能：按清单把 Clash 配置、PF 三道墙（Windows：防火墙三套规则）、守护、更新器（仅 macOS）、IPv6 守护、Chrome 描述文件（Windows：Chrome/Edge 注册表策略）、时区装成参考机那样，并逐项证明。
不能：建节点（去 vps 仓库）、清账号数据（去 reset 仓库）、改硬件指纹、保证账号不被风控、覆盖 Safari 以外的浏览器策略（Safari 靠 PF UID 规则，Firefox 未覆盖）。
