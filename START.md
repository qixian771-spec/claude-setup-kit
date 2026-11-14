# START：给 AI 的傻瓜防漏总手册（用户只发这一个链接）

你（AI）刚收到的是 <https://github.com/qixian771-spec/claude-setup-kit>。用户要的是把电脑配成"参考机"那样稳妥用 Claude。**禁止嫌麻烦半路总结收尾，禁止漏掉隐私开关、浏览器策略或时区，禁止遇到小提示就罢工停下！**

## ⚡ 防偷懒 4 步极速流水线（任何 AI 照这 4 步做到底，绝不会漏！）

> Windows 把下面的 `python3` 换成 `py -3`（路径一律用正斜杠 `/`）。如果国内没开代理连不上 GitHub，先让用户把现有 Clash 的**系统代理**打开再 `git clone`；完全没代理的新机器让用户在手机/别的电脑点 GitHub 页面 **Code → Download ZIP** 拷过来解压（Mac 首次双击若被拦，到 系统设置 → 隐私与安全性 点"仍要打开"）。

1. **第 1 步：自动认路 + 自动关后台遥测（你直接跑，不用先追问一堆问题！）**
   ```sh
   git clone https://github.com/qixian771-spec/claude-setup-kit
   cd claude-setup-kit
   python3 scripts/auto_init.py
   python3 scripts/mirror_check.py
   ```
   - `auto_init.py` 会**自动探测**当前 Clash 正在用的出口节点、本机网卡与已有守护写入 `mirror.params.json`，并**自动备份且补齐 `~/.claude/settings.json` 的 14 项官方隐私静音开关**（已有设置不覆盖，无需密码）。
   - 看完结果后，只问用户还没明确的事：**走哪条路线**（**A 建节点** / **B 配这台电脑** / **C 彻底清理换号** / **D 全套从零**）、是否同意装系统防泄露规则与关 IPv6（Windows 顺便确认时区，默认 `Pacific Standard Time`）。
   - 若 Clash 还没导入本套件配置（S1 未全绿）：把用户现有的 **1 个节点参数**（VLESS / Trojan / Shadowsocks `ss` / SOCKS5 等任意协议都支持！只有主出口被 Google 误判成中国时才需第 2 节点 `NODE2`）写成私有目录 JSON，跑 `python3 scripts/render.py --component clash --nodes <节点.json>`，让用户在 Clash Verge「新建 → 本地」导入、开启服务模式与 TUN 模式、选定主出口节点，再跑一次 `python3 scripts/auto_init.py --exit-node <主出口节点名>`。

2. **第 2 步：双击 1 次《一键安装全部》（禁止拆成十几轮折腾用户！）**
   - **macOS**：让用户双击一次 **`installers/一键安装全部.command`**（只输 1 次开机密码，自动装完 PF 三道墙 S2–S4 + 地址更新器 S5 + 自检守护 S6 + IPv6 守护 S7 + 体检工具 S8；已装过的自动跳过，不怕重跑！），再双击一次 **`installers/Chrome策略.mobileconfig`**（到 系统设置 → 通用 → 设备管理 点安装后完全退出重开 Chrome）并把系统时区调到节点所在国。
   - **Windows**：确认 Clash Verge 已安装**服务模式**且 TUN 已开后，让用户双击一次 **`installers\win\一键安装全部.cmd`**（点 1 次 UAC，自动完成：识别本机全部物理网卡 + **关闭全部物理网卡 IPv6 并开启每分钟防复开守护** + 防火墙三套规则 + 自检守护 + Chrome/Edge 防泄露策略 + 体检脚本 + 时区 + 14 项官方隐私静音开关！）。装完**保持安装状态**（只有用户明确说要打游戏撤回防护时才用 `一键撤回全部.cmd`）。

3. **第 3 步：处理其余待办与可选询问项（用 `next_step.py` 逐项扫尾，别自己猜）**
   - 运行 `python3 scripts/next_step.py`（退出码 `3` 是正常提示下一步，**不是报错**！退出码 `0` 表示全部通过）。
   - 如果遇到 `❓ 需要 sudo`（例如用户跳过了更新器 S5）：不要罢工，也不要自己敲 `sudo`，让用户双击一次只读的 `installers/提权对账.command`，再跑 `python3 scripts/next_step.py --input installers/logs/mirror-sudo-latest.json` 即可继续！
   - **桌面版自动更新（可选项，默认不锁）**：若 `desktop.updater` 发现本机已有待装更新包，先克隆跑一次 `claude-client-full-reset/scripts/desktop_update_audit.py` 用大白话告诉用户包里改了什么与安全判断，再按推荐二选一简单问用户：`1. 不关闭自动更新（推荐）` / `2. 关闭自动更新`（一句话说明原因：保持正常更新不易因版本过旧受限，只有赶工怕后台自动重启时才选关闭）。用户不关就直接往下走！
   - 若用户明确不做某一步（如不装防泄露墙 S4），把 `"skip_steps": ["S4"]` 写进 `mirror.params.json`，脚本会自动跳过并记入交付，绝不会卡死。

4. **第 4 步：交卷死闸门（没打出 `FINISH_GATE=PASSED` 绝对不准停工交差！）**
   ```sh
   python3 scripts/finish_gate.py
   ```
   - 只要它输出 `🚫 交卷被拒（FINISH_GATE=BLOCKED）`，说明**你漏项了**——必须照它列出的待办立刻补完再跑，**严禁向用户说"核心已配好，其余可选"**！
   - 只有它输出 `🎉 通关核验通过（FINISH_GATE=PASSED  核验码=...）`（`❌=0` 且 `❓=0`）后，把核验单和 `python3 scripts/mirror_check.py` 全量表贴给用户，最后按 [ippure 验收](references/ippure-acceptance.md) 请用户在浏览器打开 `https://ippure.com/claude.html` 和 `assets/webrtc-test.html` 截图确认。

---

## 1. 四条路线速查

| 路线 | 进入条件 | 做什么 | 产出 | 交回总入口时带什么 |
|---|---|---|---|---|
| **A 建节点** | 用户完全没有可用节点，准备用 VPS 自建 | `git clone https://github.com/qixian771-spec/vps-node-rebuild-3xui` 到旁边，按它的 `SKILL.md` → `references/runbook.md` 部署 3x-ui / VLESS-REALITY 并验收 | 节点参数 | 写成私有目录 JSON（**不进任何仓库**）：默认字段 `NODE1_NAME`、`NODE1_SERVER`、`NODE1_PORT`、`NODE1_UUID`、`NODE1_SNI`、`NODE1_REALITY_PUBLIC_KEY`、`NODE1_REALITY_SHORT_ID`；其它现成节点也可用 `NODE1_TYPE`（`trojan`/`ss`/`socks5`/`vmess`/`hysteria2`）或 `NODE1_PROXY` 原样对象；**仅 `NODE1` 必填**，`NODE2`/`NODE3`/`NODE4` 均可选（[cdn-backup.md](references/cdn-backup.md)） |
| **B 配 Mac** | 已有节点；macOS（需 `xcode-select -p` 有输出） | S1 导 Clash 配置开 TUN → 双击 `installers/一键安装全部.command` → 双击 `Chrome策略.mobileconfig` → S10 补官方隐私静音开关（改时区与语言为可选项） → `finish_gate.py` 通关（分步细节见 [执行手册](references/runbook.md)） | `finish_gate.py` `PASSED` + ippure 四项 | 通关核验单、全量对账表、日志路径、截图 |
| **B′ 配 Windows** | 已有节点；Windows 10/11（需装 Git for Windows、Python 3.9+ 勾 `py launcher`、Clash Verge 服务模式） | S1 导 Clash 配置开服务模式与 TUN → 双击 `installers\win\一键安装全部.cmd`（默认保留北京时间，时区可选） → `py -3 scripts/finish_gate.py` 通关（分步细节见 [Windows 手册](references/runbook-windows.md)） | 同 B | 同 B |
| **C 清理重置** | 换账号、封号后重来、深度补遥测/分流、拆检待装更新包 | `git clone https://github.com/qixian771-spec/claude-client-full-reset`，读 `SKILL.md`：`identifiers.py` 清理前后快照对比；`telemetry_routing.py` 补遥测与分流；`desktop_update_audit.py` 只读拆检更新包 | 标识对比表 / 审计报告 | `identifiers.py --compare` 退出 0 输出 |
| **D 全套从零** | 新机器或旧号彻底重来 | 顺序：C（有旧数据时）→ A（没节点时）→ B/B′ → `finish_gate.py` → ippure | 同 B | 同 B |
| **E 配 iPhone/iPad** | 已有节点或本机 Clash；要配国行/外版 iPhone（V2Box / 小火箭 / Stash / Karing） | 跑 `python3 scripts/ios_render.py --from-local-clash --copy uris --serve`（或 `--nodes`）生成四端防漏配置并弹扫码页 → `V2Box → 配置 → + → 扫描二维码` 扫主码并导入 `路由` 封死 `::/0` IPv6（或用手机网页导入小火箭/Stash/Karing）→ Safari 跑 ippure → 定位设为`永不`、先开 VPN（改地区为`美国`/改时区均为**可选项**，国行主力机按需开启；细节见 [iOS 手册](references/runbook-ios.md)） | `ios_render.py` 四格式 + ippure | 出口锁定同节点、WebRTC/DNS/IPv6 防漏 |

### 节点与 Google 智能按需分流说明（别再卡用户协议或第 2 节点！）
1. **任意协议直接用**：用户现有节点不管是 VLESS、Trojan、Shadowsocks（`ss`）、SOCKS5、VMess、Hysteria2，还是旧 Clash 配置里的节点对象，直接用 `NODE1_TYPE` 或 `NODE1_PROXY` 渲染即可。真正的死规矩只有一条：**Claude 的 `出口选择` 固定锁在同一个主出口节点，绝不含 `DIRECT`、绝不来回切**。
2. **Google 智能按需分流**：参考机设 `Google出口` 只是为了防部分机房 IP 被 Google 误判成中国（"送中"，导致 Gemini 报不支持地区）。**用户只有 1 个节点或主出口没被误判成 CN/HK 时，只填 `NODE1`（省略 `NODE2`）即可**——Google 与 Claude 安全共用主出口，`clash.google_exit` 记 `ℹ️ 单出口模式` 直接通过！只有主出口送中且有第 2 节点时才填 `NODE2`（同样支持 `ss`/`trojan` 等任意协议）。
3. **NODE4 备用 CDN 入口**：必须是 `NODE1` **同一台服务器**的 CDN 入口（出口 IP 相同）才能进 `出口选择`，且需 mihomo ≥ 1.19.29。

---

## 2. 不可越过的安全底线（由脚本自动守卫）

- **出口固定不乱切**：配置好后不为了测试去切换出口节点、不退出正在跑会话的 Clash（唯一例外：S1 初配时 `clash.base_config` ❌ 夹带了顶层代理段，征得用户同意后退出改完重开）。
- **绝不向 Anthropic / Claude 域名发网络探测**：`mirror_check` 与 `tools/check.py` 内置拦截闸门，出口与 DNS 实测只用 Cloudflare / Google 公共端点与本地 `@127.0.0.1` fake-ip 查询。
- **提权动作由用户双击完成**：AI 永远不自己敲 `sudo`；对用户说话用大白话（见 [对话模板](references/conversation.md)），每次告诉用户"双击哪个文件、做完回来说一声"。
- **诚实交付边界**：不改硬件序列号/MAC/磁盘 ID；不承诺免封号；Windows 不做精确 IP 更新器（用整段防火墙 + Clash 规则）；Firefox 无策略模板；共用 CDN 域名靠 Clash 规则分流。永远不把真实 IP、节点密钥、私人路径提交进任何仓库。
