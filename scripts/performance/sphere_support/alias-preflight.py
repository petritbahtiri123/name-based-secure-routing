"""Existing aliases only; bounded, read-only preflight. No credentials inspected."""
import pathlib,sys,subprocess,json,shlex,datetime
BASE=pathlib.Path(__file__).resolve().parent
HOSTS={'source.example.invalid':('client', '192.0.2.11'),'destination.example.invalid':('server','192.0.2.12')}
REMOTE='''import os,pwd,socket,subprocess,json
p=subprocess.run(['/usr/bin/sudo','-i','--','/usr/bin/id','-u'],capture_output=True,text=True,timeout=5)
r={'account':pwd.getpwuid(os.getuid()).pw_name,'uid':os.getuid(),'gid':os.getgid(),'hostname':socket.gethostname(),'ssh_connection':os.environ.get('SSH_CONNECTION'),'ssh_tty':os.environ.get('SSH_TTY'),'stdin_is_tty':os.isatty(0),'sudo_id_exit':p.returncode,'sudo_id_stdout':p.stdout.strip(),'sudo_id_stderr':p.stderr[:2000]}
print('NBSR_PREFLIGHT_JSON='+json.dumps(r))
'''
def main():
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        host=sys.argv[2]
        if host not in HOSTS:raise SystemExit('unapproved alias')
        # No -F, username override, key option, or SSH setting override.
        commands=shlex.join(['python3','-B','-c',REMOTE])+'\nexit\n'
        p=subprocess.run(['ssh',host],input=commands.encode('utf-8'),timeout=15)
        raise SystemExit(p.returncode)
    sys.path.insert(0,str(BASE/'approval-system-2026-10-16'));import bounded
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root=BASE/'execution-2026-10-16'/('alias-preflight-'+stamp);root.mkdir()
    rows={}
    for host,(short,ip) in HOSTS.items():
        output=root/host
        try:
            bounded.run([sys.executable,'-B',str(pathlib.Path(__file__).resolve()),'worker',host],output,20)
            lines=(output/'stdout.log').read_text().splitlines()
            matches=[line[len('NBSR_PREFLIGHT_JSON='):] for line in lines if line.startswith('NBSR_PREFLIGHT_JSON=')]
            if len(matches)!=1:raise ValueError('missing/ambiguous receipt')
            r=json.loads(matches[0]);connection=(r['ssh_connection'] or '').split()
            r['identity_route_pass']=r['account']=='benchmark-user' and r['uid']==r['gid']==1001 and r['hostname']==short+'.example.invalid' and len(connection)==4 and connection[2:]==[ip,'22']
            r['sudo_probe_pass']=r['sudo_id_exit']==0 and r['sudo_id_stdout']=='0'
            r['status']='PASS_READONLY_PREFLIGHT' if r['identity_route_pass'] and r['sudo_probe_pass'] else 'BLOCKED'
            rows[host]=r
        except Exception as e:rows[host]={'status':'BLOCKED','error':type(e).__name__,'evidence':str(output)}
    row={'utc':stamp,'invocation':'ssh ALIAS; existing default configuration; stdin supplies fixed read-only commands, not an interactive local terminal','hosts':rows,'all_pass':all(r['status']=='PASS_READONLY_PREFLIGHT' for r in rows.values()),'scope':'Probe success alone does not prove exact-command NOPASSWD or authorize later mutation.'}
    (root/'result.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row,indent=2));print('Evidence: '+str(root))
    raise SystemExit(0 if row['all_pass'] else 1)

if __name__ == "__main__":
    raise SystemExit("Reference only: configure and review explicit synthetic inputs before use")
