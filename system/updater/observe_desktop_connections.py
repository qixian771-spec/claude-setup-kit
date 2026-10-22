"""Bounded passive metadata observation via an existing local Mihomo Unix socket.

Never starts Claude, connects to a remote host, changes a proxy, or reads payloads.
Raw observations remain in an ignored, private directory; no controller secret output.
"""
import datetime
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from ruamel.yaml import YAML

BASE=Path(__file__).resolve().parent
CONFIG=Path.home()/'Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml'
APP='/Applications/Claude.app/Contents/'
CONTROL='/tmp/verge/verge-mihomo.sock'


def desktop_pids(raw):
    result=[]
    for line in raw.splitlines():
        parts=line.strip().split(None,1)
        if len(parts)==2 and parts[0].isdigit() and parts[1].startswith(APP):
            result.append(int(parts[0]))
    return result


def sockets(raw,pids,proxy_port):
    """Only sockets belonging to selected PIDs and pointing at the configured proxy."""
    result=set();pid=None;fd=None
    for line in raw.splitlines():
        if line.startswith('p'):
            pid=int(line[1:]);fd=None
        elif line.startswith('f'):fd=line[1:]
        elif line.startswith('n') and pid in pids and fd is not None:
            match=re.fullmatch(r'n(127\.0\.0\.1|\[::1\]):(\d+)->(127\.0\.0\.1|\[::1\]):(\d+)',line)
            if match and int(match[4])==proxy_port:
                result.add((pid,fd,str(ipaddress.ip_address(match[1].strip('[]'))),int(match[2])))
    return result


def snapshot(proxy_port):
    raw=subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True,timeout=5)
    pids=desktop_pids(raw)
    if not pids:raise RuntimeError('No existing Desktop process; will not start one')
    run=subprocess.run(['/usr/sbin/lsof','-nP','-a','-p',','.join(map(str,pids)),
                        '-iTCP','-Fpfn'],capture_output=True,text=True,timeout=5)
    if run.returncode not in (0,1) or run.stderr.strip():
        raise RuntimeError('Socket inventory failed; attribution refused')
    return sockets(run.stdout,pids,proxy_port)


def attributed(connections,before,after):
    endpoints={(ip,port) for _,_,ip,port in before&after}
    for conn in connections:
        meta=conn.get('metadata',{})
        if meta.get('network')!='tcp':continue
        try:
            endpoint=(str(ipaddress.ip_address(meta.get('sourceIP',''))),int(meta.get('sourcePort',0)))
        except (ValueError,TypeError):continue
        if endpoint not in endpoints:continue
        host=meta.get('host') or '(host unavailable)'
        if not isinstance(host,str) or len(host)>253 or (host!='(host unavailable)' and not re.fullmatch(r'[A-Za-z0-9_.-]+',host)):
            raise ValueError('Unexpected host metadata; observation refused')
        up,down=conn.get('upload'),conn.get('download')
        if type(up) is not int or type(down) is not int or min(up,down)<0:
            raise ValueError('Invalid traffic counters')
        ident=conn.get('id')
        if not isinstance(ident,str) or not ident:raise ValueError('Missing connection identity')
        yield ident,host.lower(),up,down


class LocalControl(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(4)
        self.sock.connect(CONTROL)


def read_connections(secret):
    c=LocalControl('localhost',timeout=4)
    try:
        c.request('GET','/connections',headers={'Authorization':'Bearer '+secret})
        response=c.getresponse();body=response.read(4*1024*1024+1)
        if response.status!=200 or len(body)>4*1024*1024:
            raise RuntimeError('Local controller refused or response too large')
        data=json.loads(body)
        if not isinstance(data.get('connections'),list):raise ValueError('Invalid connection inventory')
        return data['connections']
    finally:c.close()


def main():
    cfg=YAML(typ='safe').load(CONFIG.read_text())
    if cfg.get('external-controller-unix')!=CONTROL or cfg.get('mixed-port')!=7890:
        raise ValueError('Local controller/port changed; configuration review required')
    secret=cfg.get('secret')
    if not isinstance(secret,str) or not secret:raise ValueError('Missing local controller credential')
    directory=BASE/'private-observation'
    directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid!=os.getuid() or directory.stat().st_mode&0o077:
        raise ValueError('Unsafe observation directory')
    stamp=datetime.datetime.now(datetime.timezone.utc)
    output=directory/(stamp.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report={'status':'IN_PROGRESS','started_utc':stamp.isoformat(),'samples':0,
            'method':'existing local proxy counters + Desktop socket intersection before/after each read',
            'duration_target_seconds':120,'packet_capture':False,'tls_decrypted':False,
            'payloads_collected':False,'claude_requests_generated':False,'destinations':[]}
    state={}
    with os.fdopen(fd,'w') as file:
        def save():
            file.seek(0);json.dump(report,file,ensure_ascii=False,indent=2);file.write('\n');file.truncate();file.flush()
        save();start=time.monotonic();deadline=start+120
        try:
            while time.monotonic()<deadline:
                before=snapshot(7890);connections=read_connections(secret);after=snapshot(7890)
                for ident,host,up,down in attributed(connections,before,after):
                    if ident in state:
                        row=state[ident]
                        if row['host']!=host or up<row['last_up'] or down<row['last_down']:
                            raise ValueError('Connection metadata changed unexpectedly')
                        row.update(last_up=up,last_down=down)
                    else:state[ident]={'host':host,'first_up':up,'first_down':down,'last_up':up,'last_down':down}
                report['samples']+=1
                if report['samples']%10==0:print('Observed samples:',report['samples'],flush=True)
                time.sleep(min(2,max(0,deadline-time.monotonic())))
            report['status']='COMPLETE_METADATA_ONLY'
        except Exception as error:
            report['status']='INCOMPLETE';report['error_type']=type(error).__name__
            raise
        finally:
            totals={}
            for row in state.values():
                target=totals.setdefault(row['host'],{'host':row['host'],'connections':0,'observed_upload_delta':0,'observed_download_delta':0})
                target['connections']+=1
                target['observed_upload_delta']+=row['last_up']-row['first_up']
                target['observed_download_delta']+=row['last_down']-row['first_down']
            report['destinations']=sorted(totals.values(),key=lambda x:x['host'])
            report['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            report['elapsed_seconds']=round(time.monotonic()-start,2)
            save()
    print(json.dumps({'report':str(output),'status':report['status'],'samples':report['samples'],
                      'destinations':report['destinations']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Configuration/parser exceptions can contain sensitive source excerpts.
        print('Observation stopped:',type(error).__name__)
        raise SystemExit(1)
