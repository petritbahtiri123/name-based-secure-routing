"""In-unit resource guard; systemd owns/terminates all descendant sessions."""

import json, os, pathlib, shutil, signal, subprocess, sys, time

from plan import ROOT



def disk_guard(root):

    total=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())

    if total>256*1024**2 or shutil.disk_usage(root).free<2*1024**3:raise RuntimeError('remote disk guard')

    available=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024

    if available<2*1024**3:raise RuntimeError('host memory reserve')

    return total



def main():

    from remote_ops import security_snapshot

    role=sys.argv[sys.argv.index('--role')+1]

    security_snapshot(role)

    from tls_lifetime import gate

    gate(role,120,public=True)

    root=pathlib.Path(ROOT);disk_guard(root);started=time.monotonic();failure=None

    child=subprocess.Popen([sys.executable,*sys.argv[1:]],stdin=sys.stdin,stdout=sys.stdout,stderr=sys.stderr)

    try:

        while child.poll() is None:

            disk_guard(root)

            if time.monotonic()-started>=55:raise TimeoutError('endpoint work limit')

            time.sleep(.2)

        return child.returncode

    except BaseException as e:

        failure=type(e).__name__

        child.terminate()

        try:child.wait(timeout=5)

        except subprocess.TimeoutExpired:child.kill()

        # Returning lets KillMode=control-group reap descendants in other sessions.

        return 125

    finally:

        role=sys.argv[sys.argv.index('--role')+1]

        (root/('evidence/run07/guard-'+role+'.json')).write_text(json.dumps({'failure':failure,'elapsed':time.monotonic()-started,'exit':child.poll()}))



if __name__=='__main__':raise SystemExit(main())
