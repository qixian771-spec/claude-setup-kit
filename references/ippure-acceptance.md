# ippure 验收：四项怎么看、怎么记

最终验收页面：<https://ippure.com/claude.html>。用**要验收的那个浏览器**打开（Chrome 装了描述文件就用 Chrome；Safari 另测一次），等它跑完，整页截图。AI 不能用自己的内置浏览器代替——内置浏览器不读 Chrome 的管理策略。

## 四项与通过标准

| 项 | 页面上看什么 | 通过 | 对应 mirror_check |
|---|---|---|---|
| 出口 IP | `claude.com 出口 IP` 与 `claude.ai 出口 IP` 两个卡片 | 两个相同，都是节点所在国家/城市（不是中国），与 `net.exit_ip` 的 `出口 … loc=` 一致 | `net.exit_ip` |
| WebRTC | "WebRTC 隐私泄露隐患" | 徽标 **未发现真实 IP 泄露**；正文"暂无 WebRTC 数据，可能浏览器已拦截或禁用"是策略生效的正常表现 | `chrome.policy`、`browser.webrtc`、`pf.020` |
| DNS | "DNS 区域泄露隐患" 列表 | 每条解析器归属地都是国外（参考机：全部 Cloudflare 美国），徽标 **DNS 伪装正常**；不能出现国内运营商 | `dns.upstream`、`clash.dns`、`dns.local53` |
| 中文环境风险分 | 页面下方评分 | 没有硬门槛；记录分数与各项来源。参考机 24/100：时区 0、浏览器语言 +24（zh 排第一）、字体检测中 | `sys.timezone`、`sys.language` |

四项都要截到。分数区在页面下方，要滚到底再截一张。

## 分数项怎么降（都是可选）

| 评分来源 | 分值 | 怎么改 | 影响 |
|---|---|---|---|
| 时区为中国 | 30 | 系统设置 → 通用 → 日期与时间：关"自动设置"，选节点所在时区 | 日历/时钟显示变；参考机已是 America/Los_Angeles |
| 浏览器语言首位中文 | 24 | 系统设置 → 通用 → 语言与地区：把 English 拖到第一位 | **界面变英文**；参考机**没改**（用户决定不改） |
| 中文字体 | 20 | 无法改：macOS 自带 PingFang 等中文字体，删不掉也不该删 | — |
| Intl 区域 / UTC+8 偏移 / emoji | 10 / 8 / 8 | 随时区与语言变 | — |

语言顺序是 `sys.language`（ℹ️ 仅记录，不影响退出码）。要改也只改顺序，不删中文。

## 记录格式（交付里照抄）

```markdown
| ippure 项 | 结果 | 证据 |
|---|---|---|
| 出口 IP | claude.com / claude.ai 均 <IP> <城市> | 截图 1 |
| WebRTC | 未发现真实 IP 泄露（暂无 WebRTC 数据） | 截图 1 |
| DNS | N 个解析器全部 <提供商/国家>，DNS 伪装正常 | 截图 1 |
| 中文环境分 | NN/100（时区 x，语言 y，字体 z） | 截图 2 |
```

附上同一时刻的 `python3 scripts/mirror_check.py` 全量输出（`合计` 行 ❌ 必须为 0）。

## 常见的"看起来过了其实没过"

- 出口 IP 对但 DNS 列表里混着一条国内解析器：`clash.dns` 的 `nameserver` 没全部带 `#出口分组`，或系统 DNS 没被 TUN 劫持（`dns.local53` 会 ❌）。
- WebRTC 显示"未发现泄露"但 `chrome.policy` ❌：那是 PF 封了 STUN 端口在兜底，少了一层；装描述文件后重开 Chrome 再测。
- 用 AI 的内置浏览器测出来全过：不算，那不是用户的浏览器。
- 只截了上半页：分数项没证据，记"未验证"。
