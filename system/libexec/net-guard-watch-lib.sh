# Card N3: pure helpers for net-guard-watch (no side effects; unit-tested).

# Age in seconds of the newest APPLIED run in the updater's stdout log,
# or "none" when the log has no APPLIED run with a start time.
applied_age() {
    log=$1 now=$2
    ts=$(grep -F '"status": "APPLIED"' "$log" | grep -F '"started_utc"' | tail -1 |
         sed -E 's/.*"started_utc": "([0-9T:-]{19})[^"]*".*/\1/')
    if [ -z "$ts" ]; then echo none; return 0; fi
    then_epoch=$(date -j -u -f '%Y-%m-%dT%H:%M:%S' "$ts" '+%s')
    echo $((now - then_epoch))
}

# Notify on a new problem, a changed problem, or every 30 minutes while it lasts.
should_notify() {
    state=$1 message=$2 previous=$3 last_notify=$4 now=$5
    [ "$state" != OK ] || { echo no; return 0; }
    if [ "$previous" != "$state	$message" ] || [ $((now - last_notify)) -ge 1800 ]; then echo yes; else echo no; fi
}

# Card N7: Clash health from its local control socket (read-only).
EXPECTED_EXIT='{{EXIT_NODE}}'
CLASH_SOCKET='/tmp/verge/verge-mihomo.sock'

# "mode" field of GET /configs, or "unknown" when the JSON has none.
clash_mode() {
    mode=$(printf '%s' "$1" | grep -oE '"mode":"[^"]*"' | head -1 | sed -E 's/^"mode":"([^"]*)"$/\1/')
    echo "${mode:-unknown}"
}

# "now" field of GET /proxies/<group>, or "unknown".
clash_exit() {
    now=$(printf '%s' "$1" | grep -oE '"now":"[^"]*"' | head -1 | sed -E 's/^"now":"([^"]*)"$/\1/')
    echo "${now:-unknown}"
}
