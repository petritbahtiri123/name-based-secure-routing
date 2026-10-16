"""Offline source-archive validation; never extracts or changes permissions."""
import hashlib,io,tarfile

def verify_archive(wire,inventory):
    if len(wire)>8*1024**2 or not 0<len(inventory)<=440:raise ValueError('archive bound')
    for name,row in inventory.items():
        if name.startswith('/') or ':' in name or chr(92) in name or any(x in ('','.','..','.git') for x in name.split('/')):raise ValueError('path')
        if row['mode'] not in (0o644,0o755):raise ValueError('mode')
    seen=set();total=0
    with tarfile.open(fileobj=io.BytesIO(wire),mode='r:') as archive:
        for entry in archive:
            if entry.name not in inventory or entry.name in seen or not entry.isfile() or entry.linkname:raise ValueError('inventory/type')
            row=inventory[entry.name]
            if entry.mode!=row['mode'] or entry.size!=row['size'] or not 0<=entry.size<=4*1024**2:raise ValueError('metadata')
            total+=entry.size
            if total>8*1024**2:raise ValueError('source bound')
            body=archive.extractfile(entry).read(entry.size+1)
            if len(body)!=entry.size or hashlib.sha256(body).hexdigest()!=row['sha256']:raise ValueError('bytes')
            seen.add(entry.name)
    if seen!=set(inventory):raise ValueError('missing')
    return {'files':len(seen),'source_bytes':total,'archive_bytes':len(wire)}
