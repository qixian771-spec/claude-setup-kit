# iPhone / iPad（iOS）部署手册：对齐电脑端环境

苹果手机与电脑处于封闭沙盒，电脑无法通过 USB 直接修改 iPhone 的系统防火墙，但可以通过本仓库的 [ios_render.py](../scripts/ios_render.py) 一键把**同一套主出口节点、Google 智能分流、关 IPv6、拦 WebRTC STUN 与 116 条分流/遥测规则**转换为 iOS 主流客户端配置，配合通用剪贴板 / iPhone 镜像 / 隔空投送导入手机。

---

## 0. 国行 + 国内手机卡防漏规矩（Safari 网页版 & 原生 Claude / Claude Duet App）

1. **为什么 iOS 16.4+ 国行机插 `+86` 电话卡也能用原生 App（区分必做防漏项 & 可选项）**：
   - 从 **iOS 16.4+** 起，苹果已在系统底层废弃第三方 App 读取 SIM 卡运营商的接口（`CTCarrier` 统一返回占位值 `65535` / `--`），沙盒也禁止读取硬件销售型号，因此普通 App 无法直接拿到 `+86` 运营商编码；日常更需防住的是**定位、本地网络与未走 VPN 直连**。
   - **仅用 Safari 网页版时**：在 Safari 登录官网后点底部分享 →「添加到主屏幕」，同时把 `设置 → 隐私与安全性 → 定位服务 → Safari 网站` 设为「永不」。
   - **需要使用原生 `Claude App`（含远程控制）或 `Claude Duet` 时**：
     1. **美区 App Store 下载（必做）**：使用美区 Apple ID 下载 `Claude` 与 `Claude Duet`（订阅走网页端，勿切回国区商店内购）。
     2. **锁死定位与本地网络（必做）**：`设置 → 隐私与安全性 → 定位服务` 中把 `Claude`、`Claude Duet`、`Safari 网站` 均设为 **「永不」**，并在两款 App 设置中关闭 **「本地网络」**，阻止读取 GPS 与路由器热点 MAC。
     3. **先连稳 VPN 再打开 App / 点推送（必做）**：确认状态栏已有 `VPN` 图标后再打开 App 或点开 `Claude Duet` 通知（可在 `设置 → VPN → 客户端旁 ⓘ` 按需开启「按需连接」）。
     4. **改系统「地区」与「时区」（均为可选项，按使用者习惯决定）**：打开 `设置 → 通用 → 语言与地区`，语言保留「简体中文」，可将 **「地区」改为 `美国`**（仅影响地域标识，不改界面语言）；**时区默认可保留北京时间**（国行主力机不动时区也算通过，仅在专用机上按需进 `日期与时间` 改美国时区）。
2. **主账号与小号分机锁死固定出口**：
   - 电脑和主力手机登录同一个账号时共用同一个主出口（如 `--from-local-clash`）；不同账号之间切勿混用同一个出口 IP。
3. **只读边界与隐私保护**：
   - 生成的配置目录只放在仓库外私有目录，权限收紧为 `0700`/`0600`；节点服务器地址、UUID、密码、密钥永远不进任何仓库，也不向控制台打印。

---

## 1. 一键生成并扫码导入 iOS 四端配置（V2Box / 小火箭 / Stash / Karing）

### 方式 A：你这台电脑已经跑着本套件 Clash 配置（最省事，直接弹二维码）

```sh
python3 scripts/ios_render.py --from-local-clash --out /tmp/ios-config-private --copy uris --serve
```

- 自动从本机运行中的 Clash 提取当前主出口（及已启用的 `Google出口`），生成 4 份文件并写入电脑剪贴板，并在电脑浏览器弹出导入页（默认 `600` 秒后自动关闭；也可加 `--nodes <私有节点.json>` 代替 `--from-local-clash`）：
  - **页面第 1 个主二维码（最推荐）**：直接给 **`V2Box → 配置（Configs） → + → 扫描二维码（Scan QR Code）`** 扫码即刻导入 **`Claude专用-<主节点>`**（无需同一 Wi-Fi）；
  - **页面第 2 个网页二维码**：同一 Wi-Fi 下用苹果「相机」扫码在 Safari 打开，提供绿色一键复制链接按钮、**`② 一键导入 V2Box 防漏路由（封死 IPv6 + 大陆直连）`**（`v2box://routes?multi=`）、`v2box://install-config`、Shadowrocket / Stash / Karing 一键导入，以及最底部折叠框内的 Xray 116 条分流完整 JSON：
    - `v2box-xray.json`：V2Box 高级完整 JSON（内置 `UseIPv4` 防 AAAA、阻断 `::/0` IPv6、封死 `3478/5349/19302` STUN、Google 与国内直连分流）
    - `v2box-uris.txt`：带 `Claude专用-` / `Claude谷歌-` 前缀的标准分享链接
    - `stash-karing-clash.yaml`：Stash / Karing 原生 Clash YAML（已自动剔除桌面 `PROCESS-NAME` 规则）
    - `shadowrocket.conf`：小火箭 Shadowrocket 专用 `.conf` 配置（`ipv6 = false`、`prefer-ipv6 = false`、`DEST-PORT` STUN 拦截、`选定主出口` 禁 `DIRECT`）

### 方式 B：用独立节点 JSON 文件生成

```sh
python3 scripts/ios_render.py --nodes <私有节点.json> --out /tmp/ios-config-private --copy uris --serve
```

- 参数格式与电脑端 `render.py --nodes` 完全一致（支持 VLESS-REALITY、Trojan、Shadowsocks `ss`、SOCKS5、VMess 与 `NODE1_PROXY` 原样对象）。如果只需写入剪贴板不弹网页，去掉 `--serve` 即可；Windows 把 `python3` 换成 `py -3`。

---

## 2. 导入 V2Box / 小火箭 / Stash / Karing（国行无「iPhone 镜像」也能 1 秒搞定）

- **苹果沙盒限制**：国行 iPhone 官方禁用「iPhone 镜像」，且未越狱 iOS 严禁电脑通过 USB 读写第三方 VPN App 数据库；直接用手机扫 `--serve` 页面上的二维码是最稳做法：
1. **V2Box 中文版（第 1 推荐：打开 App 直接扫码 + 路由封死 IPv6 与国内自动分流）**：
   - 打开 `V2Box` → 点底部 **`配置`（Configs）** → 点右上角 **`+`** → 选 **`扫描二维码`（Scan QR Code）** → 直接扫电脑页最上方的 **第 1 个大二维码** → 列表立即新增 **`Claude专用-<主节点>`** → 点一下选中它。
   - **封死 IPv6 + 国内自动分流（重要：V2Box 只导入节点时不启用任何分流规则，默认是全局代理）**：
     - **一键导入（最省事）**：同一 Wi-Fi 下用苹果「相机」扫电脑网页第 2 个二维码 → 点 **`② 点我复制防漏分流路由并打开 V2Box`**（会自动复制 3 条路由并唤起 V2Box；如未自动弹窗，进 **`路由`** → 右上角 `+` / 导入图标 → **从剪贴板导入**）；
     - **手动添加（务必全小写并把域名与 IP 拆成两条）**：进底部 **`路由`（Route / Routing）**（或 `设置 → 路由`）→ 点右上角 **`+`** 分 3 条保存启用：
       1. 类型选 **`IP`**、标签选 **`阻止`（block）**、IP 填 **`::/0`**（封死 IPv6）；
       2. 类型选 **`Domain`**（域名）、匹配 **`keyword`**、标签选 **`直连`（direct）**、填入 **`geosite:cn`**（与 `geosite:private`）；
       3. 类型选 **`IP`**、匹配 **`keyword`**、标签选 **`直连`（direct）**、IP 填 **`geoip:cn`**（严格全小写，含 `geoip:private`）。
     - 确认 3 条规则右侧开关全部开启、连接模式未设为「全局」，再回 **`主页`（Home）** 开关重连一次即可！
   - 若偏好通过 Safari 网页复制节点：用手机页 **`① 点我复制节点链接并打开 V2Box`** → `V2Box → 配置 → + → 从剪贴板导入 v2ray uri`（弹窗点「允许粘贴」）。

### Shadowrocket（小火箭）/ Stash / Karing

1. 若已跑 `--serve`，同一 Wi-Fi 下用苹果「相机」扫电脑网页第 2 个二维码，在 Safari 展开底部「小火箭 / Stash / Karing」一键导入即可（自带完整 116 条防漏规则与禁用 IPv6）。
2. 没跑 `--serve` 时，也可把私有目录里的 `shadowrocket.conf` 或 `stash-karing-clash.yaml` **隔空投送（AirDrop）** 到 iPhone，再分别在各客户端启用配置并核对 `IPv6` 关闭。

---

## 3. 手机系统核对与最终验收

1. **关闭苹果 iCloud 专用代理**：手机打开 `设置 → 你的名字 → iCloud → 专用代理`（若有开）改为关闭，避免苹果自带中转节点和你固定美国 IP 打架。
2. **系统地区与时区（均为可选项，如实交付即可）**：
   - **地区（可选）**：如需降低地区差异感，可在 `设置 → 通用 → 语言与地区` 把「地区」设为 **`美国`**（语言保留简体中文，不改界面文字）；保留默认也可正常使用。
   - **时区（可选，国行主力机默认保留北京时间）**：日常主力机保留**北京时间**，不在外挂任何虚假入口；`ippure` 会显式扣掉“时区不一致”的分数（如实记录即可：出口 IP / DNS / WebRTC / IPv6 已防漏，时区按用户意愿保留北京时间）。仅在专用工作机上需要时关闭自动设置并选美国时区。
3. **Safari 跑通验收，再使用原生 App 或桌面网页图标**：
   - 连上 V2Box / 小火箭 / Karing 后，先用 **Safari** 访问 `https://ippure.com/claude.html`。
   - 核对硬指标：**① 出口 IP 与指定美国节点一致；② WebRTC 无真实公网/IPv6 候选；③ DNS 全走国外且无国内运营商解析器，且未漏出 `2408:/2409:/240e:` 等国内 IPv6**。
   - **如何单独确认国内自动分流生效**：像 `ippure.com` 本身是国外网站，分流正常时它本来就走美国出口 IP；请再用 Safari 打开国内查 IP 页（如在 `https://www.baidu.com` 搜索 `IP` 或访问 `https://myip.ipip.net`），显示为你本地国内宽带/手机卡 IP、而 `ippure.com` 显示美国出口 IP，即表示国内外自动分流完全正常。
   - 验收通过后，即可打开美区原生 **`Claude App` / `Claude Duet`**，或用 Safari 打开官网「添加到主屏幕」。
