# START：给 AI 的总手册（用户只发这一个链接）

你（AI）刚收到的是 <https://github.com/qixian771-spec/claude-setup-kit>。用户要的是：把他们的电脑配成"参考机"那样用 Claude——可能包括建节点、配 Mac 环境、清理重置。本页告诉你先问什么、走哪条路、每条路的产出和交回点。**每一步只认机器输出（对账表、日志、退出码），不认你自己的判断。**

## 0. 先做三件事

**先确认能打开 GitHub**：在国内没有任何代理时 `github.com` 多半连不上（连接被重置或超时），`git clone` 会在第一步就卡住。用户已经有 Clash/节点的，让他们先把 Clash 的**系统代理**打开再克隆（这不违反"出口不切换"——这里只是开关系统代理，不动节点）。完全没有代理、也没有节点的新机器（A 路线从零）拿不到仓库，让用户用能上网的手机或另一台电脑在 GitHub 页面点 **Code → Download ZIP**，把 zip 拷过来解压，之后所有命令一样跑（`mirror_check`、`next_step` 不依赖 git）。不要自己找第三方镜像站替用户下载。

```sh
git clone https://github.com/qixian771-spec/claude-setup-kit
cd claude-setup-kit
python3 scripts/mirror_check.py
```

Windows 上把 `python3` 换成 `py -3`、路径用反斜杠（`py -3 scripts\mirror_check.py`）。Windows 需要先装两样：**Git for Windows**（<https://git-scm.com/download/win>，默认选项即可）和 **Python 3.9+**（<https://www.python.org/downloads/windows/>，安装时勾上 *py launcher*）；装好后在 PowerShell 里 `git --version` 和 `py -3 --version` 都有输出才继续。还要装 **Clash Verge（Windows 版）**并在 设置 里**安装服务模式**（TUN 的硬前提，弹 UAC），装法见 [Windows 手册](references/runbook-windows.md) S1 第 1 步。这三样都让用户自己点安装包。

`mirror_check` 的"只读"是指**不改任何东西**：它会向 `www.cloudflare.com`（出口 IP 与国家）、`1.1.1.1` / `ns1.google.com`（DNS 上游）发探测，还会在本机解析 `www.cloudflare.com`（`dig @127.0.0.1` 与系统解析器，证明 DNS 走了 Clash；这两条 `--no-network` 也不跳过），不碰任何 Anthropic 地址；查 PF 时用 `sudo -n`，没有免密 sudo 的机器那几项显示 ❓（提示会告诉你用 `sudo python3 scripts/mirror_check.py --only …` 重跑，不要当 ❌）。网络受限时加 `--no-network`，两项出口检查会变 ❓。

问到出口节点名后，立刻把它写进仓库根目录的 `mirror.params.json`（git 忽略；机器上**已经有** IPv6 守护的才要写 `"ipv6_guard_label"`：先 `ls /Library/LaunchDaemons | grep -i ipv6`，有就把那个文件名去掉 `.plist` 填进去——参考机是 `com.niuniu.ipv6-guard`；新机器不写，用默认 `local.ipv6-guard`。写错或不写，`daemon.ipv6` 会 ❌，安装器会因脚本已存在拒装（EXIT=72），卸载器会因 label 不符拒卸（也是 EXIT=73：这个码统一表示"前置不符"，日志里写明是哪一样），都不会动已有守护）：

```json
{"exit_node": "<出口节点名>"}
```

没有这个文件时 `mirror_check` 和 `next_step` 都会在第一行提醒你——那时的 ✅/❌ 是对着参考机的节点名算的，不作数。Windows 机器还要写网卡名：`{"exit_node": "<出口节点名>", "network_services": ["以太网"]}`（名字照『网络连接』里显示的，中文系统通常是 `以太网` / `WLAN`）。

退出码的意思：`mirror_check` 0 = 全 ✅，1 = 有 ❌，2 = 有 ❓；`next_step` **3 = 正常，打印了现在要做的那一步**，0 = 全部步骤通过去做 ippure，2 = 跑不了（manifest 不一致或 mirror_check 崩了）。看到 3 不是失败。

然后问用户一句话（已经说过的不要再问）："你要的是哪种：**A 建节点**（还没有可用节点）、**B 配这台 Mac**（已有节点）、**C 清理重置 / 换账号 / 补遥测开关**、**D 全套从零**？" 以及出口节点名、是否同意装防火墙规则与描述文件、是否同意关 IPv6；**Windows 还要问时区**：一键安装会把系统时区改成 `mirror.params.json` 里 `timezone_win` 的值（默认 `Pacific Standard Time`，美国太平洋），用户要别的就先写进去，不想改就不用一键、分步跳过 S7。

仓库根目录的 `AGENTS.md` 是账号级的通用交付标准，它自己写明"不授予额外写入/发布权限、遵守本仓库具体规则"——所以下面的硬规则优先，尤其是"要密码的安装由用户双击"，AI 不自己 sudo。

硬规则（任何路线都适用）：出口节点固定不切、不退出 Clash、不关 TUN；不向 Anthropic / Claude 地址做直连试探；所有写系统的动作由用户双击或在界面里点，你只渲染、读日志、对账；没有兜底——安装器拒绝就停下报告。

## 1. 路线

| 路线 | 进入条件 | 做什么 | 产出 | 交回总入口时带什么 |
|---|---|---|---|---|
| **A 建节点** | 用户没有可用节点，有 VPS 或准备买 | `git clone https://github.com/qixian771-spec/vps-node-rebuild-3xui` 到本仓库旁边，读它的 `SKILL.md` → `references/runbook.md`，按它的任务卡部署 3x-ui / VLESS-REALITY 并验收 | 节点参数（服务器、端口、UUID、SNI、REALITY 公钥与 short-id） | 写成 JSON：键名用本仓库 `templates/clash-profile.template.yaml` 里的 `NODE1_NAME`、`NODE1_SERVER`、`NODE1_PORT`、`NODE1_UUID`、`NODE1_SNI`、`NODE1_REALITY_PUBLIC_KEY`、`NODE1_REALITY_SHORT_ID`（NODE1 是 VLESS-REALITY；trojan 用 `NODE2_NAME`、`NODE2_SERVER`、`NODE2_PORT`、`NODE2_PASSWORD`、`NODE2_SNI`；socks5 用 `NODE3_NAME`、`NODE3_SERVER`、`NODE3_PORT`、`NODE3_USERNAME`、`NODE3_PASSWORD`；`render.py` 对缺的键直接报错；NODE1 和 NODE2 必填，NODE3 可选——不给 NODE3_* 时模板里 socks5 那段和它在分组里的成员会被整个去掉）；文件放私有目录，**不进任何仓库** |
| **B 配 Mac** | 有节点参数；macOS | 本仓库 [执行手册](references/runbook.md) S1–S12；每做完一步跑 `python3 scripts/next_step.py`，它会说下一步做什么 | `mirror_check` 全 ✅ + ippure 四项 | 全量对账表、日志路径、截图 |
| **B′ 配 Windows 10/11** | 有节点参数；Windows | 本仓库 [Windows 手册](references/runbook-windows.md) S1–S9；命令用 `py -3 scripts\mirror_check.py`、`py -3 scripts\next_step.py`；S1 之后双击 `installers\win\一键安装全部.cmd`（一次 UAC 装完 S2–S7），测完或要打游戏前双击 `一键撤回全部.cmd` | 同 B | 同 B |
| **C 清理重置** | 换账号、封号后重来、要关遥测/补分流 | `git clone https://github.com/qixian771-spec/claude-client-full-reset`，读它的 `SKILL.md` → `references/agent-runbook.md`；用它的 `identifiers.py` 在清理前后快照证明 ID 换了；`telemetry_routing.py` 补遥测开关与分流规则 | 清理验收 + 标识对比表 | `identifiers.py --compare` 退出 0 的输出 |
| **D 全套从零** | 新机器或要"和参考机一模一样" | 顺序：C（可选，只在有旧数据时）→ A（没有节点时）→ B → ippure | 同 B | 同 B |

路线之间的衔接：A 的产出直接喂给 B 的 S1（`render.py --component clash --nodes <JSON>`）——**至少要两个节点**：`NODE1` 给 Claude 固定出口，`NODE2`（可再加 `NODE3`）给 Google 系域名用的 `Google出口` 分组，因为 Google 的地理库常把面向国内用户的机房 IP 判成中国，Gemini 会提示"不支持该地区"；Claude 出口不受影响。C 做完后 B 的 S9（Chrome）与 S1 都要重新对账，因为清理会动浏览器与 Clash 之外的 Claude 数据但不动系统防护。

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

不改硬件序列号 / MAC / 磁盘 ID；不保证账号不被风控；Windows 侧不做精确 IP 更新器（只做整段墙 + Clash 域名规则）；Firefox 没有策略模板；Claude 走共用 CDN 的域名靠 Clash 规则而不是防火墙。
