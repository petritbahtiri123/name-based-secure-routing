import hashlib,json,subprocess,sys,time
from pathlib import Path
from linux_exit import observe_owned_exit
rows=[]
for expected in [0,7,-9]:
 child=subprocess.Popen([sys.executable,"-c", "import time; time.sleep(10)" if expected<0 else f"import sys; sum(range(100000)); sys.exit({expected})"])
 try:
  if expected<0: child.kill()
  deadline=time.monotonic()+5
  while True:
   observed=observe_owned_exit(child.pid)
   if observed is not None:break
   if time.monotonic()>=deadline:raise RuntimeError("exit observation deadline")
   time.sleep(.01)
  assert observed==expected and child.returncode is None
  first=Path(f"/proc/{child.pid}/stat").read_text()
  repeated=observe_owned_exit(child.pid)
  second=Path(f"/proc/{child.pid}/stat").read_text()
  assert repeated==expected and child.returncode is None
  a=first[first.rfind(")")+2:].split();b=second[second.rfind(")")+2:].split()
  assert a[0]==b[0]=="Z" and a[19]==b[19]
  assert a[11:13]==b[11:13]
  joined=child.wait(timeout=5)
  assert joined==expected and not Path(f"/proc/{child.pid}").exists()
  rows.append(dict(expected=expected,observed=observed,repeated=repeated,terminal_state=a[0],identity_retained=True,cpu_ticks_retained=True,explicit_join=joined,proc_removed_after_join=True))
 finally:
  if child.returncode is None:
   try:child.kill()
   except ProcessLookupError:pass
   child.wait(timeout=5)
print(json.dumps(dict(classification="LINUX_LIFECYCLE_COMPATIBILITY_ONLY",helper_sha256=hashlib.sha256(Path("/case/linux_exit.py").read_bytes()).hexdigest(),results=rows)))
