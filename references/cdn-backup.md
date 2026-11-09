# 给自己的节点加一个 Cloudflare CDN 备用入口（对应模板里可选的 NODE4）

> 这是"直连入口被墙时的急救门"，不是日常线路：走 Cloudflare 用不上三网优化线路，晚高峰会慢。平时仍然直连 NODE1，
> 只有 NODE1 连不上时才在 Clash 里手动切到 NODE4。**Claude 看到的出口 IP 不变**——CDN 只改"你 → 服务器"这一段，
> "服务器 → Claude"那一段还是同一台机器。

## 0. 两条铁规（和 START.md 一致）

1. NODE4 必须是 **NODE1 同一台服务器**上的入口。只有这样它的出口 IP 才和 NODE1 相同，才可以放进「出口选择」当备用成员。
   指向别的服务器的 CDN 节点，出口 IP 不同，**不准**放进「出口选择」（Claude 的规则会走到它，等于换了出口）。
2. NODE4 **不选中**。渲染出来的配置里它只是「出口选择」列表里的一个成员；切不切由用户在界面里决定，AI 不替用户切。

另外：客户端内核要 mihomo ≥ 1.19.29（`clash.xhttp_core` 会查）。Windows 的 Clash Verge 2.4.4 带的 1.19.17 不支持 XHTTP，
导入带 NODE4 的配置会整份加载失败——先升级，或者渲染时不给 `NODE4_*`。

## 1. 架构

```
平时：      本机 ──直连──▶ 服务器:主力端口（VLESS-REALITY，NODE1） ──▶ Claude 看到 服务器出口 IP
被墙时备用： 本机 ──▶ Cloudflare（优选 IP，443） ──▶ 服务器:2083（VLESS+XHTTP+TLS，NODE4） ──▶ 同一个出口 IP
```

- 为什么是 XHTTP：REALITY 过不了 CDN；WebSocket 在 Xray 26 已标记弃用，官方推荐 XHTTP。
- 新入口用**独立的 xray 进程和独立账号**（如 `xray-cdn.service`），不碰主力入站、不重启主力进程——主力线路零中断。
- 源站端口用一个空闲端口（下面用 2083 举例），Cloudflare 这一侧用 Origin Rules 把 443 改成回源 2083。
- 源站防火墙只对 Cloudflare 的 IP 段放行 2083：别人扫不到，墙也探测不到源站入口。

## 2. 你需要

- 一个域名，DNS 托管在 Cloudflare（免费版够用）。建议用看起来像静态资源的子域名，如 `static.<域名>`。
- 已经在跑主力节点的服务器（NODE1 那台），root 或 sudo，`certbot`，和面板同款的 `xray` 二进制。
- 本机先有能用的代理（否则 Cloudflare 后台和 GitHub 都可能打不开）。

## 3. Cloudflare 后台（用户自己登录做，AI 不替用户登录）

1. DNS：`static.<域名>` → A 记录指向服务器 IPv4，**开启代理（橙云）**。
2. SSL/TLS：加密模式 **Full (strict)**。不开 Always Use HTTPS（下一步的证书验证要走 HTTP 回源）。
3. Rules → Origin Rules：匹配 `static.<域名>`，**目标端口改写为 2083**。
4. Security → Bots：关闭 Bot Fight Mode（否则代理流量会被挑战）。

## 4. 服务器（AI 可以经 SSH 做；每一步贴输出）

1. 证书（Let's Encrypt，私钥不离开服务器）：
   ```sh
   certbot certonly --standalone --preferred-challenges http --http-01-port 2083 -d static.<域名>
   ```
   验证流量经 Cloudflare 的 HTTP 回源到 2083（所以第 3 步不能开 Always Use HTTPS）。
   续期钩子里先 `systemctl stop xray-cdn`、续完 `start`；`certbot renew --dry-run` 要通过。
2. 专用账号与配置：`useradd -r -s /usr/sbin/nologin xray-cdn`；`/etc/xray-cdn/config.json` 写一个 VLESS 入站，
   `network: xhttp`，`path` 随机（如 `/` + 16 位随机），TLS 用上面的证书，监听 `0.0.0.0:2083`；出站 freedom，
   `domainStrategy: UseIPv4`（IPv6 全程禁止）。新 UUID 和 path **只存在服务器上**，不抄进任何仓库。
3. systemd：`xray-cdn.service` 以 `xray-cdn` 用户运行同款 xray 二进制，`xray run -test -c ...` 通过后再 `enable --now`。
4. 防火墙：2083 **只放行 Cloudflare 的 IPv4 段**（官方列表 `https://www.cloudflare.com/ips-v4`），不要放行 IPv6 段。
5. 有外层安全组的服务商（如 LisaHost）还要在面板里放行 TCP 2083。

## 5. 验收（每条要有命令输出）

| # | 验收 | 怎么验 |
|---|---|---|
| 1 | SSL 真的是 Full (strict) | 先用自签证书起服务，经 Cloudflare 访问应得 **526**；换 Let's Encrypt 后 526 消失 |
| 2 | 源站只对 Cloudflare 开门 | 从非 Cloudflare 的公网 IP 连 2083 被拒 |
| 3 | 主力零中断 | 动手前后主力 xray 进程 PID 一致，主力节点延迟测试有数值 |
| 4 | 新入口能用、出口不变 | 用**隔离的临时内核**（不是正在用的 Clash）连 NODE4，访问 `www.cloudflare.com/cdn-cgi/trace` 看 `ip=`，必须等于 NODE1 的出口；`www.gstatic.com/generate_204` 返回 204 |
| 5 | **测试不碰 Claude** | 全程不访问任何 Anthropic / Claude 域名（套件的 `mirror_check` 和 `check.py` 对这条有机器闸门） |

Cloudflare 分配的 IP 在部分运营商下连不上时，客户端 `NODE4_SERVER` 填 **优选 IP**，`NODE4_HOST` 填域名（它同时进
`servername` 和 `xhttp-opts.host`）。

## 6. 渲染

把参数写进节点 JSON（和 NODE1/NODE2 放一起，不进仓库）：

```json
{"NODE4_NAME": "<名字>-CDN", "NODE4_SERVER": "<Cloudflare 优选 IP>", "NODE4_PORT": "443",
 "NODE4_UUID": "<服务器上的 UUID>", "NODE4_HOST": "static.<域名>", "NODE4_PATH": "/<随机 path>"}
```

`python3 scripts/render.py --component clash --nodes <JSON>` 后对账 `--only clash.xhttp_core,clash.exit`：
前者 ✅（或没有 NODE4 时 ℹ️），后者 `now` 仍是 NODE1。

## 7. 风险（提前告诉用户）

- 慢：晚高峰走 Cloudflare 会卡，所以只当备用。
- Cloudflare 能看到连接的目标域名（如 `claude.ai:443`），看不到内容（Claude 本身是端到端 HTTPS）。
- 拿 CDN 当代理隧道处于 Cloudflare 条款的灰色地带，账号有被处理的可能。
- Xray 可能打印弃用警告（如 VLESS 无 flow），原样贴给用户，不隐藏。
