"""Materialize the disclosed 440-file exact-commit presentation, never a full clone."""
import hashlib, io, json, os, pathlib, stat, subprocess, tarfile
from plan import SHA

def run(root,*args,input=None):
    p=subprocess.run(['git','--no-optional-locks','-C',str(root),*args],input=input,
                     capture_output=True,timeout=20)
    if p.returncode: raise RuntimeError('git '+args[0]+': '+p.stderr.decode(errors='replace')[:200])
    return p.stdout

def archive_entries(wire, inventory):
    if len(wire)>8*1024**2 or len(inventory)!=440: raise ValueError('source bounds')
    rows={}
    with tarfile.open(fileobj=io.BytesIO(wire),mode='r:') as t:
        for e in t:
            n=e.name; p=pathlib.PurePosixPath(n)
            if n in rows or n not in inventory or not e.isfile() or e.linkname or p.is_absolute() or any(x in ('..','.git') for x in p.parts) or '\\' in n or ':' in n:
                raise ValueError('source entry')
            v=inventory[n]; body=t.extractfile(e).read()
            if e.size!=v['size'] or e.mode!=v['mode'] or e.mode not in (0o644,0o755) or hashlib.sha256(body).hexdigest()!=v['sha256']:
                raise ValueError('source hash/mode')
            rows[n]=body
    if set(rows)!=set(inventory): raise ValueError('missing source')
    return rows

def verify(root, inventory):
    if run(root,'rev-parse','HEAD').decode().strip()!=SHA: raise ValueError('commit')
    tree={}
    for row in run(root,'ls-tree','-rz',SHA).split(b'\0'):
        if row:
            meta,name=row.split(b'\t');mode,kind,oid=meta.decode().split()
            tree[name.decode()]=(mode,oid)
    index={}
    for row in run(root,'ls-files','--stage','-z').split(b'\0'):
        if row:
            meta,name=row.split(b'\t');mode,oid,stage=meta.decode().split()
            if stage!='0':raise ValueError('index stage')
            index[name.decode()]=(mode,oid)
    if index!=tree:raise ValueError('index/tree')
    flags={r[2:].decode():chr(r[0]) for r in run(root,'ls-files','-v','-z').split(b'\0') if r}
    actual=set();allowed_dirs={parent.as_posix() for n in inventory for parent in pathlib.PurePosixPath(n).parents}
    for parent,dirs,files in os.walk(root,followlinks=False):
        if pathlib.Path(parent)==root:dirs[:]=[n for n in dirs if n!='.git']
        for n in [*dirs,*files]:
            p=pathlib.Path(parent)/n;rel=p.relative_to(root).as_posix();mode=p.lstat().st_mode
            if stat.S_ISDIR(mode):
                if rel not in allowed_dirs:raise ValueError('unexpected directory')
            elif stat.S_ISREG(mode):actual.add(rel)
            else:raise ValueError('special source entry')
    if actual!=set(inventory): raise ValueError('unexpected/missing materialized file')
    for n,v in inventory.items():
        p=root/n
        if any(q.is_symlink() for q in (p,*p.parents)) or flags.get(n)!='H': raise ValueError('selected flag/alias')
        if os.name!='nt' and stat.S_IMODE(p.stat().st_mode)!=v['mode']:raise ValueError('physical mode')
        body=p.read_bytes();oid=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
        if tree[n]!=(format(v['mode'] | 0o100000,'o'),oid) or hashlib.sha256(body).hexdigest()!=v['sha256']:raise ValueError('selected content/mode')
    if any(flags[n]!='S' for n in set(tree)-set(inventory)):raise ValueError('excluded flag')
    if run(root,'status','--porcelain','--untracked-files=all'):raise ValueError('dirty source')
    return dict(commit=SHA,materialized=440,excluded=len(tree)-440,full_object_closure=False)

def stage(root, wire, inventory, pack):
    rows=archive_entries(wire,inventory)
    root.mkdir(exist_ok=False)
    run(root,'init','--quiet');run(root,'config','core.autocrlf','false');run(root,'config','core.filemode','false' if os.name=='nt' else 'true')
    run(root,'index-pack','--stdin',input=pack)
    (root/'.git/shallow').write_text(SHA+'\n')
    run(root,'update-ref','HEAD',SHA);run(root,'read-tree',SHA)
    names=[r for r in run(root,'ls-files','-z').split(b'\0') if r]
    run(root,'update-index','--skip-worktree','-z','--stdin',input=b'\0'.join(names)+b'\0')
    for n,b in rows.items():
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);p.chmod(inventory[n]['mode'])
    run(root,'update-index','--no-skip-worktree','-z','--stdin',input=b'\0'.join(n.encode() for n in rows)+b'\0')
    return verify(root,inventory)
