// claude-mac-env-mirror — bind this script to the imported profile in Clash Verge.
// It sets the DNS block (fake-ip, DoH via {{EXIT_GROUP}} for Claude and friends, CN DIRECT) and
// prepends the STUN REJECT rules; it also deletes prepend-rules, so put rules in the profile itself.
function main(config) {
  config.dns = {
  "enable": true,
  "listen": "127.0.0.1:53",
  "ipv6": false,
  "use-hosts": true,
  "enhanced-mode": "fake-ip",
  "fake-ip-range": "198.18.0.1/16",
  "fake-ip-filter": [
    "geosite:cn",
    "geosite:private",
    "+.lan",
    "+.local",
    "+.localhost",
    "time.*.com",
    "ntp.*.com",
    "+.pool.ntp.org",
    "*.srv.nintendo.net",
    "stun.*.*"
  ],
  "respect-rules": false,
  "default-nameserver": [
    "https://223.5.5.5/dns-query#DIRECT"
  ],
  "proxy-server-nameserver": [
    "https://223.5.5.5/dns-query#DIRECT"
  ],
  "direct-nameserver": [
    "https://223.5.5.5/dns-query#DIRECT"
  ],
  "nameserver": [
    "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
  ],
  "nameserver-policy": {
    "+.anthropic.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.claude.ai": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.claude.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.claude.app": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.claudeusercontent.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.claudemcpcontent.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.sentry.io": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.sentry-cdn.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.statsig.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.statsigapi.net": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.statsigcdn.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.featuregates.org": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.featureassets.org": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.assetsconfigcdn.org": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.prodregistryv2.org": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "+.beyondwickedmapping.org": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "http-intake.logs.us5.datadoghq.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "browser-intake-us5-datadoghq.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "cloudflare-dns.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "storage.googleapis.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "registry.npmjs.org": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "github.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "raw.githubusercontent.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "formulae.brew.sh": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "fonts.googleapis.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "fonts.gstatic.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "cdnjs.cloudflare.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "cdn.jsdelivr.net": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "cdn.tailwindcss.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "code.jquery.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "unpkg.com": [
      "https://1.1.1.1/dns-query#{{EXIT_GROUP}}"
    ],
    "geosite:cn": [
      "https://223.5.5.5/dns-query#DIRECT"
    ],
    "geosite:private": [
      "rcode://name_error"
    ]
  }
};
  const block = ["DST-PORT,3478,REJECT", "DST-PORT,5349,REJECT", "DST-PORT,19302,REJECT"];
  config.rules = block.concat((config.rules || []).filter(rule => !block.includes(rule)));
  delete config["prepend-rules"];
  return config;
}
