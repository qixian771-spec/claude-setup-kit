# claude-setup-kit

把电脑配成"参考机"那样用 Claude 的**总入口**：建节点、配 Mac 环境、清理重置三件事，一个链接发给任何 AI 就能做，而且**每一步都有机器判定**（对账表、日志、退出码），能力差的模型也漏不了步。MIT 开源。

## 发给 AI 的一段话（复制粘贴即可）

> 请打开 https://github.com/qixian771-spec/claude-setup-kit ，先读 START.md，按它说的克隆仓库、运行 `python3 scripts/mirror_check.py`，然后问我要走哪条路线（建节点 / 配这台 Mac / 清理重置 / 全套从零）。之后每一轮都运行 `python3 scripts/next_step.py`，它说什么你就做什么，让我动手的地方按 references/conversation.md 的话术告诉我。硬规则：出口节点不许切换、不许退出 Clash、不许向 Anthropic 地址直连试探；所有要密码的安装由我双击文件完成，你只读日志和对账；每一步都要贴对账输出，不要自己说"做好了"。最后按 references/ippure-acceptance.md 让我截图验收。

## 它由三部分组成

| 部分 | 仓库 | 管什么 |
|---|---|---|
| 总入口 + Mac 环境镜像 | **本仓库** | `START.md` 选路；`manifest.json` 36 个组件；`mirror_check.py` 只读对账；`next_step.py` 告诉 AI 现在做什么；Clash 配置模板、PF 三道墙、守护、更新器、IPv6 守护、Chrome 描述文件的双击安装器；ippure 验收 |
| 建节点 | [vps-node-rebuild-3xui](https://github.com/qixian771-spec/vps-node-rebuild-3xui) | VPS、3x-ui、VLESS-REALITY 节点部署与验收 |
| 清理重置 | [claude-client-full-reset](https://github.com/qixian771-spec/claude-client-full-reset) | Claude 本地数据与标识清理、清理前后 ID 快照对比、遥测开关与分流补齐 |

START.md 会在需要时让 AI 克隆另外两个仓库并按它们的手册走；用户不需要再分别发链接。

## 本仓库的工具

| 东西 | 作用 |
|---|---|
| `START.md` | AI 的总手册：先问什么、四条路线、产出与交回、交付清单 |
| `manifest.json` | 36 个组件的契约（怎么验证、失败下一步）+ 12 个步骤的顺序、前置、安装器、对用户说的话 |
| `scripts/mirror_check.py` | 一条命令只读对账，✅/❌/❓/ℹ️/👉 表与退出码 0/1/2 |
| `scripts/next_step.py` | 读对账结果，按步骤顺序打印"现在做什么"；全过时打印 ippure 验收任务 |
| `scripts/render.py` | 把 `system/`、`templates/` 的占位符模板按本机参数渲染到独立目录 |
| `templates/clash-profile.template.yaml` | 参考机的 Clash 配置（112 条规则）：Claude 固定出口分组 + Google 专用分组（Gemini 不被判成中国）+ 遥测/CDN/第三方规则，节点全部占位符 |
| `installers/安装*.command`、`卸载.command` | 用户双击安装/卸载（先拒绝覆盖再写、pf.conf 备份+语法检查、装后验证），输出写 `installers/logs/` |
| `installers/Chrome策略.mobileconfig` | Chrome WebRTC/DoH 策略描述文件（手工写 Managed Preferences 会被系统清掉） |
| `assets/webrtc-test.html` | 本地 WebRTC 候选检查 |
| `tools/check.py`、`tools/redact_check.py` | 打包检查；脱敏扫描（公网 IP、UUID、凭据、私人路径 0 命中才能提交） |
| [references/runbook.md](references/runbook.md) / [runbook-windows.md](references/runbook-windows.md) | Mac 路线 S1–S12、Windows 路线 S1–S9 的逐步手册与情景推演 |
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
