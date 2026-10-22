# claude-mac-env-mirror

把一台 Mac 的 Claude 网络与浏览器环境配成参考机那样，并且**每一项都能被机器验证**的 Agent Skill。MIT 开源。

## 三个仓库分工

| 仓库 | 管什么 |
|---|---|
| [vps-node-rebuild-3xui](https://github.com/qixian771-spec/vps-node-rebuild-3xui) | 服务器端：建 VPS、3x-ui、出节点 |
| **claude-mac-env-mirror**（本仓库） | 本机端：Clash Verge 固定出口与 fake-ip DNS、PF 三道墙、自检守护、地址更新器、IPv6 守护、Chrome 描述文件、时区；对账与 ippure 验收 |
| [claude-client-full-reset](https://github.com/qixian771-spec/claude-client-full-reset) | 清理重置：Claude 本地数据与标识、遥测开关、分流补齐 |

## 它怎么防止 AI 漏步

| 东西 | 作用 |
|---|---|
| [manifest.json](manifest.json) | 36 个组件的契约：每项怎么验证、失败了下一步是什么 |
| `scripts/mirror_check.py` | 一条命令只读对账，输出 ✅/❌/❓/ℹ️/👉 表和退出码 0/1/2；AI 不贴它的输出就不能说"做好了" |
| `scripts/render.py` | 把 `system/`、`templates/` 里的占位符模板按本机参数渲染到独立目录（USER/HOME/UID/TUN/出口分组与节点/网卡/守护 label） |
| `installers/安装*.command` | 用户双击安装（先拒绝覆盖再写、pf.conf 备份+语法检查、装后验证），全部输出写 `installers/logs/`，AI 读日志判定 |
| `installers/Chrome策略.mobileconfig` | Chrome 的 WebRTC/DoH 策略用描述文件装（手工写 Managed Preferences 会被系统清掉） |
| `assets/webrtc-test.html` | 本地 WebRTC 候选检查 |
| `tools/redact_check.py` | 仓库脱敏扫描：公网 IP、UUID、凭据、私人路径 0 命中才能提交 |
| [references/ippure-acceptance.md](references/ippure-acceptance.md) | 最终以 <https://ippure.com/claude.html> 四项为验收标准 |

## 交给其他 AI 执行

> 阅读 SKILL.md 和 references/runbook.md，先 `python3 scripts/mirror_check.py` 只读对账，再按手册 S1–S12 顺序执行；每一步只做那一步的组件，贴对应 id 的对账输出；需要 root 的安装由我双击 installers 里的文件，你读 installers/logs 的日志；出口节点不许切换，不许碰 Anthropic 地址；最后按 references/ippure-acceptance.md 做四项验收。

## 快速验证

需要 macOS 与系统自带 Python 3（3.9 起，无第三方依赖）：

```sh
python3 scripts/mirror_check.py
```

```sh
python3 -m unittest discover -s tests && python3 tools/check.py && python3 tools/redact_check.py
```

本机参数放在仓库根目录的 `mirror.params.json`（git 忽略），例如 `{"exit_node": "你的节点名"}`。节点密钥只通过 `render.py --nodes <文件>` 传入，不进仓库。

## 边界

不建节点、不清账号数据、不改硬件指纹、不保证账号不被风控；Firefox 没有策略模板（只有 PF UID 规则兜底）；Claude 走共用 CDN 的域名（downloads.claude.ai、statsig）靠 Clash 规则而不是 PF。每一步做不到的事都要在交付里写明。
