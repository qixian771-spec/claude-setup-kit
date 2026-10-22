"""Audit fixed Claude DNS names through the existing proxy; optionally add IPs.

No vendor requests, direct DNS, app launches, address deletion, or PF reload.
Run as the desktop user, not root. --apply requires existing sudo authorization.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urlencode
import uuid

from ruamel.yaml import YAML
from observe_desktop_connections import CONFIG

BASE = Path(__file__).resolve().parent
HOSTS = ('claude.ai', 'api.anthropic.com', 'bridge.claudeusercontent.com')
RESOLVERS = {'cloudflare-dns.com': '/dns-query', 'dns.google': '/resolve'}
ANCHOR = 'com.apple/010.local.claude-direct-wall'
TABLE = 'claude_wall_targets'
RULES = Path('/etc/pf.anchors/local.claude-direct-wall')
BACKUP_DIR = Path('/var/db/ClaudeDirectWall')
LOCK = '/var/run/claude-direct-wall/update.lock'
# Network deadlines remain finite; process budget also covers macOS scheduling/startup.
CONNECT_TIMEOUT = 10
TRANSFER_TIMEOUT = 25
PROCESS_TIMEOUT = 40
QUERY_WORKERS = 4
ACTIVE_RULES = (
    'pass out quick on {{TUN}} from any to <claude_wall_targets> no state label "claude-wall-tun"\n'
    'block drop out quick inet from any to <claude_wall_targets> label "claude-wall-ipv4"\n'
    'block drop out quick inet6 from any to <claude_wall_targets> label "claude-wall-ipv6"\n'
)
RULE_BODY = (
    'pass out quick on {{TUN}} to <claude_wall_targets> no state label "claude-wall-tun"\n'
    'block drop out quick inet to <claude_wall_targets> label "claude-wall-ipv4"\n'
    'block drop out quick inet6 to <claude_wall_targets> label "claude-wall-ipv6"\n'
)


class Rejected(ValueError):
    """Only fixed, locally authored rejection reasons, safe for public reports."""


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def exact_ip(value):
    require(isinstance(value, str) and '/' not in value and '%' not in value, 'Not an exact IP')
    ip = ipaddress.ip_address(value)
    require(ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback), 'Non-public IP')
    if ip.version == 6:
        require(not (ip.ipv4_mapped or ip.sixtofour or ip.teredo)
                and ip not in ipaddress.ip_network('64:ff9b::/96'), 'Embedded IP rejected')
    return str(ip)


def ordered(values):
    return sorted(values, key=lambda v: (ipaddress.ip_address(v).version, int(ipaddress.ip_address(v))))


def domain(value):
    require(isinstance(value, str), 'Invalid domain')
    value = value.lower().removesuffix('.')
    require(len(value) <= 253 and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p)
                                    for p in value.split('.')), 'Invalid domain')
    return value


def dns_diagnostics(data):
    """Record typed DNS flags only, never remote free-text comments or response data."""
    if not isinstance(data, dict):
        return {'object': False}
    result = {'object': True, 'flags': {}}
    for name in ('Status', 'TC', 'CD', 'AD'):
        if name not in data:
            result['flags'][name] = {'type': 'missing'}
            continue
        value = data[name]
        kind = type(value)
        if kind is bool:
            row = {'type': 'bool', 'value': value}
        elif kind is int and 0 <= value <= 4294967295:
            row = {'type': 'int', 'value': value}
        elif value is None:
            row = {'type': 'null'}
        else:
            row = {'type': 'invalid'}
        result['flags'][name] = row
    return result


def parse_dns(data, host, qtype):
    require(host in HOSTS and qtype in (1, 28), 'Unapproved query')
    require(isinstance(data, dict), 'DNS response is not an object')
    require(type(data.get('Status')) is int, 'DNS status missing or not an integer')
    require(data['Status'] == 0, 'DNS status is not NOERROR')
    require(data.get('TC') is False, 'DNS truncated or TC missing/invalid')
    require(data.get('CD') is False, 'DNS validation disabled or CD missing/invalid')
    question = data.get('Question')
    require(isinstance(question, list) and len(question) == 1, 'Invalid question')
    require(domain(question[0]['name']) == host and type(question[0]['type']) is int
            and question[0]['type'] == qtype, 'Question mismatch')
    answers = data.get('Answer')
    require(isinstance(answers, list) and 0 < len(answers) <= 64, 'Empty/oversized answer')
    cname = {}; addresses = {}; ttls = {}
    for record in answers:
        kind = record.get('type')
        require(type(kind) is int, 'Invalid answer type')
        if kind == 46:  # DNSSEC signature is not address evidence.
            continue
        require(kind in (5, qtype), 'Unexpected answer type')
        owner = domain(record['name'])
        ttl = record['TTL']
        require(type(ttl) is int and 0 < ttl <= 2147483647, 'Invalid TTL')
        ttls.setdefault(owner, []).append(ttl)
        if kind == 5:
            target = domain(record['data'])
            require(owner not in cname or cname[owner] == target, 'Conflicting CNAME')
            cname[owner] = target
        else:
            ip = exact_ip(record['data'])
            require(ipaddress.ip_address(ip).version == (4 if qtype == 1 else 6), 'Address family mismatch')
            addresses.setdefault(owner, set()).add(ip)
    owner = host; chain = []
    while owner in cname:
        require(owner not in chain and len(chain) < 8 and owner not in addresses, 'Invalid CNAME chain')
        chain.append(owner); owner = cname[owner]
    chain.append(owner)
    require(set(cname) | set(addresses) <= set(chain), 'Unrelated answer owner')
    ips = addresses.get(owner, set())
    require(0 < len(ips) <= 32, 'Missing/oversized terminal address set')
    return {'addresses': ordered(ips), 'min_ttl': min(t for n in chain for t in ttls[n]), 'chain': chain}


def query(resolver, host, qtype):
    require(resolver in RESOLVERS and host in HOSTS and qtype in (1, 28), 'Unapproved query')
    url = 'https://' + resolver + RESOLVERS[resolver] + '?' + urlencode({'name': host, 'type': qtype})
    # Disable curlrc, explicit proxy, no bypass, no redirects or retries, HTTPS only.
    command = ['/usr/bin/curl', '--disable', '--silent', '--show-error', '--fail',
               '--proxy', 'http://127.0.0.1:7890', '--noproxy', '', '--proto', '=https',
               '--connect-timeout', str(CONNECT_TIMEOUT), '--max-time', str(TRANSFER_TIMEOUT), '--max-filesize', '262144',
               '-H', 'accept: application/dns-json', url]
    started = time.time()
    clock_started = time.monotonic()
    response_digest = None
    diagnostics = None
    try:
        result = subprocess.run(command, check=True, capture_output=True, timeout=PROCESS_TIMEOUT)
        require(len(result.stdout) <= 262144, 'Oversized DNS body')
        response_digest = hashlib.sha256(result.stdout).hexdigest()
        body = json.loads(result.stdout)
        diagnostics = dns_diagnostics(body)
        parsed = parse_dns(body, host, qtype)
    except Exception as error:
        # Fixed query metadata only: never serialize stderr, response bodies or exception text.
        error.audit_context = {'operation': 'dns_query', 'resolver': resolver, 'host': host,
                               'qtype': qtype, 'elapsed_seconds': round(time.monotonic() - clock_started, 3)}
        if isinstance(error, subprocess.TimeoutExpired):
            error.audit_context['process_timeout_seconds'] = PROCESS_TIMEOUT
        if isinstance(error, subprocess.CalledProcessError):
            error.audit_context['curl_exit_code'] = error.returncode
        if response_digest is not None:
            error.audit_context['response_sha256'] = response_digest
        if diagnostics is not None:
            error.audit_context['dns_response'] = diagnostics
        raise
    return dict(parsed, resolver=resolver, host=host, qtype=qtype, queried_at=started,
                elapsed_seconds=round(time.monotonic() - clock_started, 3),
                response_sha256=response_digest, dns_response=diagnostics)


def collect():
    observations = []
    # Interleave the two providers instead of bursting six connections at one provider.
    jobs = [(r, h, q) for h in HOSTS for q in (1, 28) for r in RESOLVERS]
    with ThreadPoolExecutor(max_workers=QUERY_WORKERS) as pool:
        for round_number in (1, 2):
            if round_number == 2:
                time.sleep(2)
            pending = [pool.submit(query, *job) for job in jobs]
            try:
                for future in as_completed(pending):
                    observations.append(dict(future.result(), round=round_number))
            except Exception as error:
                for future in pending:
                    future.cancel()  # Running calls keep their own bounded deadlines.
                if hasattr(error, 'audit_context'):
                    error.audit_context['round'] = round_number
                raise  # No second round or retry after incomplete evidence.
    return observations


def confirm(observations, now):
    expected = {(r, h, q, n) for r in RESOLVERS for h in HOSTS for q in (1, 28) for n in (1, 2)}
    indexed = {}
    for row in observations:
        key = (row['resolver'], row['host'], row['qtype'], row['round'])
        require(key in expected and key not in indexed, 'Missing/duplicate/unapproved observation')
        require(0 <= now - row['queried_at'] < min(row['min_ttl'], 300), 'Expired evidence')
        ips = {exact_ip(ip) for ip in row['addresses']}
        require(0 < len(ips) <= 32, 'Invalid observation set')
        indexed[key] = ips
    require(set(indexed) == expected, 'Incomplete evidence')
    result = set()
    for host in HOSTS:
        for qtype in (1, 28):
            sets = [indexed[r, host, qtype, n] for r in RESOLVERS for n in (1, 2)]
            require(all(s == sets[0] for s in sets), 'DNS sources/rounds disagree')
            result.update(sets[0])
    require(len(result) <= 128, 'Too many confirmed targets')
    return result


def parse_rules(text):
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    require(len(lines) == 4 and '\n'.join(lines[1:]) + '\n' == RULE_BODY, 'Firewall body changed')
    match = re.fullmatch(r'table <claude_wall_targets> persist \{ ([^{}]+) \}', lines[0])
    require(match is not None, 'Unexpected table declaration')
    values = {exact_ip(v.strip()) for v in match[1].split(',')}
    require(0 < len(values) <= 128, 'Invalid persistent targets')
    return values


def render_rules(values):
    values = {exact_ip(v) for v in values}
    require(0 < len(values) <= 128, 'Invalid target count')
    return ('# Confirmed targets, additive updates only. See address-update evidence.\n'
            'table <claude_wall_targets> persist { ' + ', '.join(ordered(values)) + ' }\n' + RULE_BODY)


def plan(active, persisted, confirmed, proxies):
    require(active and persisted and confirmed, 'Empty target set')
    union = {exact_ip(v) for v in active | persisted | confirmed}
    require(len(union) <= 128, 'Accumulated target cap reached; manual review required')
    require(not union.intersection(proxies), 'Proxy node overlaps target')
    return union


def apply_update(backend, confirmed, proxies):
    active, persisted = backend.snapshot()
    union = plan(active, persisted, confirmed, proxies)
    # Persist the union first. A failure leaves existing live targets untouched.
    # An interrupted add can then be repaired without forgetting confirmed IPs.
    if persisted != union:
        backend.persist(union)
    backend.add(union)  # -T add, never replace/flush/delete or ruleset reload.
    backend.kill_states(union)
    current, saved = backend.snapshot()
    require(current == union and saved == union, 'Post-update readback mismatch')
    return {'added_live': ordered(union - active), 'retained': ordered(active), 'targets': ordered(union)}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout


def root(*args):
    return run('/usr/bin/sudo', '-n', *args)


def pf(*args):
    return root('/sbin/pfctl', *args)


def proxy_config():
    raw = CONFIG.read_bytes()
    cfg = YAML(typ='safe').load(raw)
    require(cfg.get('mode') == 'rule' and cfg.get('mixed-port') == 7890, 'Proxy mode changed')
    require(cfg.get('tun', {}).get('enable') is True and cfg['tun'].get('device') == '{{TUN}}', 'TUN changed')
    nodes = cfg.get('proxies', [])
    require(bool(nodes), 'No proxy nodes')
    ips = {exact_ip(n['server']) for n in nodes}
    groups = {g['name']: g for g in cfg['proxy-groups']}
    require(groups['{{EXIT_GROUP}}']['type'] == 'select' and groups['GLOBAL']['type'] == 'select'
            and set(groups['{{EXIT_GROUP}}']['proxies']) == {n['name'] for n in nodes}
            and groups['GLOBAL']['proxies'] == ['{{EXIT_GROUP}}'], 'Proxy group policy changed')
    return raw, ips


class SystemBackend:
    def snapshot(self):
        require('Status: Enabled' in pf('-s', 'info'), 'PF disabled')
        require('anchor "com.apple/*"' in pf('-sr'), 'Root anchor hook missing')
        require(pf('-a', ANCHOR, '-sr') == ACTIVE_RULES, 'Active rules changed')
        require(not RULES.is_symlink() and run('/usr/bin/stat', '-f', '%u:%Lp', str(RULES)).strip() == '0:644', 'Unsafe rules file')
        active = {exact_ip(v.strip()) for v in pf('-a', ANCHOR, '-t', TABLE, '-T', 'show').splitlines()}
        require(bool(active), 'Empty live table')
        return active, parse_rules(RULES.read_text())

    def persist(self, values):
        text = render_rules(values)
        original = RULES.read_bytes()
        staging = str(RULES) + '.pending-' + uuid.uuid4().hex
        backup = str(BACKUP_DIR / ('rules-before-' + uuid.uuid4().hex + '.pf'))
        with tempfile.TemporaryDirectory(prefix='claude-wall-update-') as tmp:
            p = Path(tmp) / 'rules.pf'; p.write_text(text)
            pf('-n', '-a', ANCHOR, '-f', str(p))
            require(RULES.read_bytes() == original, 'Concurrent rules change')
            root('/usr/bin/install', '-o', 'root', '-g', 'wheel', '-m', '600', str(RULES), backup)
            root('/usr/bin/install', '-o', 'root', '-g', 'wheel', '-m', '644', str(p), staging)
            require(Path(staging).read_text() == text and RULES.read_bytes() == original, 'Staging/concurrency mismatch')
            with open(staging, 'rb') as file:
                os.fsync(file.fileno())
            root('/bin/mv', '-f', staging, str(RULES))
            require(parse_rules(RULES.read_text()) == values, 'Persistent readback mismatch')

    def add(self, values):
        pf('-a', ANCHOR, '-t', TABLE, '-T', 'add', *ordered(values))

    def kill_states(self, values):
        for ip in ordered(values):
            pf('-k', '::/0' if ':' in ip else '0.0.0.0/0', '-k', ip)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Fresh DNS audit only; no firewall changes')
    mode.add_argument('--apply', action='store_true', help='Fresh audit then add confirmed targets')
    args = parser.parse_args()
    require(os.geteuid() != 0, 'Run as desktop user; individual PF commands use sudo -n')
    directory = BASE / 'address-update-reports'; directory.mkdir(exist_ok=True)
    require(not directory.is_symlink(), 'Report directory is a symlink')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = directory / (stamp + '.json')
    report = {'status': 'IN_PROGRESS', 'mode': 'apply' if args.apply else 'check',
              'claude_requests_generated': False, 'claude_restarted': False, 'direct_retry': False}
    locked = False
    try:
        report['phase'] = 'proxy_config'
        raw, proxies = proxy_config()
        backend = SystemBackend()
        report['phase'] = 'firewall_snapshot'
        active, saved = backend.snapshot()
        report['targets_before'] = ordered(active)
        report['phase'] = 'dns_collect'
        observations = collect()
        report['observations'] = observations
        report['phase'] = 'dns_confirm'
        confirmed = confirm(observations, time.time())
        union = plan(active, saved, confirmed, proxies)
        report.update(confirmed=ordered(confirmed), proposed_targets=ordered(union),
                      new_candidates=ordered(union - active), retained_not_in_current_dns=ordered((active | saved) - confirmed))
        require(CONFIG.read_bytes() == raw, 'Proxy configuration changed during audit')
        if args.apply:
            report['phase'] = 'acquire_update_lock'
            root('/bin/mkdir', '-m', '700', LOCK); locked = True
            # Repeat freshness and proxy checks under the lock; never accept saved evidence as input.
            current_raw, current_proxies = proxy_config()
            require(current_raw == raw, 'Proxy changed before apply')
            confirmed = confirm(observations, time.time())
            report['phase'] = 'apply_and_verify'
            report['applied'] = apply_update(backend, confirmed, current_proxies)
            require(CONFIG.read_bytes() == raw, 'Proxy changed during apply')
        report['status'] = 'APPLIED' if args.apply else 'CHECKED_NO_MUTATION'
        report['phase'] = 'complete'
    except Exception as error:
        report.update(status='STOPPED_OLD_TARGETS_NOT_REMOVED', error_type=type(error).__name__)
        # Only locally generated validation reasons; parser/process exceptions may contain secrets.
        if type(error) is Rejected:
            report['reason'] = str(error)
        if hasattr(error, 'audit_context'):
            report['failure_context'] = error.audit_context
        raise
    finally:
        try:
            if locked:
                root('/bin/rmdir', LOCK)
        except Exception:
            report['status'] = 'STOPPED_LOCK_CLEANUP_FAILED'
            raise
        finally:
            report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'report': str(output), 'status': report['status'],
                              'new_candidates': report.get('new_candidates', [])}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Address update stopped:', type(error).__name__)
        raise SystemExit(1)
