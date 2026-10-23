# START：给 AI 的总手册（用户只发这一个链接）

你（AI）刚收到的是 <https://github.com/qixian771-spec/claude-setup-kit>。用户要的是：把他们的电脑配成"参考机"那样用 Claude——可能包括建节点、配 Mac 环境、清理重置。本页告诉你先问什么、走哪条路、每条路的产出和交回点。**每一步只认机器输出（对账表、日志、退出码），不认你自己的判断。**

## 0. 先做三件事

```sh
git clone https://github.com/qixian771-spec/claude-setup-kit
cd claude-setup-kit
python3 scripts/mirror_check.py
```

问到出口节点名后，立刻把它写进仓库根目录的 `mirror.params.json`（git 忽略；参考机还要 `"ipv6_guard_label"`，其他机器一般不用）：

```json
{"exit_node": "<出口节点名>"}
```

没有这个文件时 `mirror_check` 会用 manifest 里参考机的默认值对账，`next_step` 会提醒你。

然后问用户一句话（已经说过的不要再问）："你要的是哪种：**A 建节点**（还没有可用节点）、**B 配这台 Mac**（已有节点）、**C 清理重置 / 换账号 / 补遥测开关**、**D 全套从零**？" 以及出口节点名、是否同意装防火墙规则与描述文件、是否同意关 IPv6。

硬规则（任何路线都适用）：出口节点固定不切、不退出 Clash、不关 TUN；不向 Anthropic / Claude 地址做直连试探；所有写系统的动作由用户双击或在界面里点，你只渲染、读日志、对账；没有兜底——安装器拒绝就停下报告。

## 1. 路线

| 路线 | 进入条件 | 做什么 | 产出 | 交回总入口时带什么 |
|---|---|---|---|---|
| **A 建节点** | 用户没有可用节点，有 VPS 或准备买 | `git clone https://github.com/qixian771-spec/vps-node-rebuild-3xui` 到本仓库旁边，读它的 `SKILL.md` → `references/runbook.md`，按它的任务卡部署 3x-ui / VLESS-REALITY 并验收 | 节点参数（服务器、端口、UUID、SNI、REALITY 公钥与 short-id） | 写成 JSON：键名用本仓库 `templates/clash-profile.template.yaml` 里的 `NODE1_NAME`、`NODE1_SERVER`、`NODE1_PORT`、`NODE1_UUID`、`NODE1_SNI`、`NODE1_REALITY_PUBLIC_KEY`、`NODE1_REALITY_SHORT_ID`（trojan/socks5 用 NODE2/NODE3 的键）；文件放私有目录，**不进任何仓库** |
| **B 配 Mac** | 有节点参数；macOS | 本仓库 [执行手册](references/runbook.md) S1–S12；每做完一步跑 `python3 scripts/next_step.py`，它会说下一步做什么 | `mirror_check` 全 ✅ + ippure 四项 | 全量对账表、日志路径、截图 |
| **C 清理重置** | 换账号、封号后重来、要关遥测/补分流 | `git clone https://github.com/qixian771-spec/claude-client-full-reset`，读它的 `SKILL.md` → `references/agent-runbook.md`；用它的 `identifiers.py` 在清理前后快照证明 ID 换了；`telemetry_routing.py` 补遥测开关与分流规则 | 清理验收 + 标识对比表 | `identifiers.py --compare` 退出 0 的输出 |
| **D 全套从零** | 新机器或要"和参考机一模一样" | 顺序：C（可选，只在有旧数据时）→ A（没有节点时）→ B → ippure | 同 B | 同 B |

路线之间的衔接：A 的产出直接喂给 B 的 S1（`render.py --component clash --nodes <JSON>`）；C 做完后 B 的 S9（Chrome）与 S1 都要重新对账，因为清理会动浏览器与 Clash 之外的 Claude 数据但不动系统防护。

## 2. 在 B 路线里你每一轮只做这三件事

```sh
python3 scripts/next_step.py
```

它会打印：现在做哪一步、哪些组件没过、让用户双击哪个文件、对用户说哪句话、做完跑哪条对账命令。照做，贴对账输出，再跑一次 `next_step.py`。它说"全部步骤通过 → 做 ippure 验收"时，按 [ippure 验收](references/ippure-acceptance.md) 让用户截两张图并记录四项。

用户需要动手的时候，照 [对话模板](references/conversation.md) 说话。

## 3. 交付

- B：`python3 scripts/mirror_check.py` 全量输出（`合计` 行 ❌=0 ❓=0）+ 每步日志 `installers/logs/*.log` 的最后几行 + chrome://policy、WebRTC、ippure 两张截图 + 没做或做不到的项（未授权跳过、Firefox、硬件指纹、共用 CDN 域名）。
- A、C：各自仓库手册规定的验收证据。
- 永远不要把节点参数、密钥、私人路径、截图里的真实 IP 写进任何仓库或公开的地方。

## 4. 做不到的事（提前告诉用户）

不改硬件序列号 / MAC / 磁盘 ID；不保证账号不被风控；Windows 版本尚未提供（见 docs/release-tasks.md 的计划）；Firefox 没有策略模板；Claude 走共用 CDN 的域名靠 Clash 规则而不是防火墙。
