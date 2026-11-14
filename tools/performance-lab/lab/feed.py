"""Passive, opt-in local delivery. No network or workload control."""
import argparse
from contextlib import closing
import asyncio
import base64
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from .adapters import MAX_BYTES, decode
from .ingestion import normalize_artifact

PACKET_LIMIT = MAX_BYTES * 2


def read_bounded(path, limit):
    if path.is_symlink() or path.is_junction():
        raise ValueError('Linked input is not supported')
    with path.open('rb') as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Input exceeds size limit')
    return raw


def inspect(raw):
    runs = normalize_artifact(raw)
    if len(runs) != 1 or not runs[0].get('stream'):
        raise ValueError('Feed requires one grouped progress snapshot')
    run = runs[0]
    # The exporter requires fully framed records; it never ships a partial line.
    try:
        obj = decode(raw)
    except ValueError:
        if not raw.endswith(b'\n'):
            raise ValueError('Wait for a complete newline-delimited snapshot')
        records = [decode(line) for line in raw.splitlines() if line.strip()]
        metadata = {}
    else:
        records = obj.get('records', [obj])
        metadata = obj.get('metadata', {})
    return run, records, metadata


def export(source, inbox, experiment):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', experiment):
        raise ValueError('Experiment ID must be 1-64 safe characters')
    raw = read_bounded(Path(source), MAX_BYTES)
    inspect(raw)
    digest = hashlib.sha256(raw).hexdigest()
    inbox = Path(inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / f'{experiment}-{digest}.packet'
    if target.exists():
        return False
    packet = dict(schema='nbsr-lab-delivery-v1', experiment=experiment,
                  sequence=time.time_ns(), exported_at=time.time(), sha256=digest,
                  artifact=base64.b64encode(raw).decode('ascii'))
    with tempfile.NamedTemporaryFile(dir=inbox, prefix='.pending-', delete=False) as f:
        staged = Path(f.name)
        f.write(json.dumps(packet, allow_nan=False).encode()); f.flush(); os.fsync(f.fileno())
    try:
        try: os.link(staged, target)
        except FileExistsError: return False
    finally:
        staged.unlink(missing_ok=True)
    return True


class Inbox:
    def __init__(self, store, directory):
        self.store, self.directory = store, Path(directory)
        self.error = None
        self.seen = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        with closing(store.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS deliveries(experiment TEXT, sequence INTEGER, sha256 TEXT, received REAL, packet TEXT, PRIMARY KEY(experiment,sequence))')

    def accept(self, wire):
        if len(wire) > PACKET_LIMIT: raise ValueError('Packet too large')
        # Packet is larger than artifact allowance because of base64 framing.
        packet = json.loads(wire, object_pairs_hook=self.unique)
        if set(packet) != {'schema','experiment','sequence','exported_at','sha256','artifact'} or packet['schema'] != 'nbsr-lab-delivery-v1':
            raise ValueError('Unsupported delivery envelope')
        experiment, sequence = packet['experiment'], packet['sequence']
        if not isinstance(experiment,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',experiment): raise ValueError('Invalid experiment ID')
        if type(sequence) is not int or not 0 < sequence < 2**63: raise ValueError('Invalid sequence')
        if type(packet['exported_at']) not in (int,float) or not 0 < packet['exported_at'] < 1e12: raise ValueError('Invalid export time')
        raw = base64.b64decode(packet['artifact'], validate=True)
        if hashlib.sha256(raw).hexdigest() != packet['sha256']: raise ValueError('Delivery hash mismatch')
        run, records, metadata = inspect(raw)
        with closing(self.store.connect()) as db, db:
            existing = db.execute('SELECT sha256,packet FROM deliveries WHERE experiment=? AND sequence=?',(experiment,sequence)).fetchone()
            if existing:
                if existing['packet'] != wire.decode('utf-8'): raise ValueError('Sequence conflict')
                return
            prior = db.execute('SELECT * FROM deliveries WHERE experiment=? ORDER BY sequence DESC LIMIT 1',(experiment,)).fetchone()
        if prior:
            if sequence <= prior['sequence']: raise ValueError('Out-of-order delivery')
            old, old_records, old_metadata = inspect(self.store.artifact(prior['sha256']))
            if old['stream']['state'] == 'final': raise ValueError('Experiment already finalized')
            if metadata != old_metadata or len(records) <= len(old_records) or records[:len(old_records)] != old_records:
                raise ValueError('Snapshot must extend the unchanged experiment prefix')
        result = self.store.ingest(raw, experiment + '.snapshot')
        if result['status'] != 'imported': raise ValueError('Snapshot quarantined')
        with closing(self.store.connect()) as db, db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)',(experiment,sequence,result['sha256'],time.time(),wire.decode('utf-8')))

    @staticmethod
    def unique(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError('Duplicate delivery key')
            result[key] = value
        return result

    def scan(self):
        self.error = None
        try:
            paths = list(self.directory.glob('*.packet'))
            if len(paths) > 4096: raise ValueError('Inbox exceeds 4096 packets; archive reviewed deliveries')
            packets = []
            budget = 32 * 1024 * 1024
            for path in paths:
                try:
                    stat = path.stat()
                    signature = (stat.st_size,stat.st_mtime_ns)
                    cached = self.seen.get(path)
                    if cached and cached[0] == signature:
                        if cached[1]: self.error = cached[1]
                        continue
                    if stat.st_size > budget:
                        self.error = 'Inbox scan budget reached; remaining packets deferred.'
                        continue
                    budget -= stat.st_size
                    wire = read_bounded(path, PACKET_LIMIT)
                    packet = json.loads(wire)
                    sequence = packet.get('sequence') if isinstance(packet,dict) else None
                    if type(sequence) is not int: raise ValueError('Invalid sequence')
                    packets.append((sequence,path,signature))
                except (OSError,ValueError,TypeError,KeyError,RecursionError):
                    self.error = 'A delivery was rejected; inspect local inbox. Previous evidence retained.'
            for _,path,signature in sorted(packets,key=lambda item:item[0]):
                issue = None
                try: self.accept(read_bounded(path, PACKET_LIMIT))
                except (OSError,ValueError,TypeError,KeyError,RecursionError):
                    issue = 'A delivery was rejected; inspect local inbox. Previous evidence retained.'
                    self.error = issue
                self.seen[path] = (signature,issue)

        except (OSError,ValueError,TypeError,KeyError):
            self.error = 'Inbox scan failed; previous evidence retained.'

    def status(self):
        with closing(self.store.connect()) as db, db:
            rows = db.execute('SELECT experiment,COUNT(*) AS updates,MAX(sequence) AS sequence FROM deliveries GROUP BY experiment').fetchall()
            result = []
            for row in rows:
                latest = db.execute('SELECT * FROM deliveries WHERE experiment=? AND sequence=?',(row['experiment'],row['sequence'])).fetchone()
                run = next((r for r in self.store.runs() if r['sha256']==latest['sha256']),None)
                state = 'invalid' if run and run['stream']['validity']=='invalid' else 'final' if run and run['stream']['state']=='final' else 'receiving' if row['updates']>=2 and time.time()-latest['received']<=30 else 'waiting' if row['updates']==1 else 'stale'
                result.append(dict(experiment=row['experiment'],updates=row['updates'],sha256=latest['sha256'],received=latest['received'],state=state))
        return dict(configured=True,feeds=result,error=self.error)

    async def watch(self):
        while True:
            await asyncio.to_thread(self.scan)
            await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,help='Explicit reviewed local full-prefix export only')
    parser.add_argument('--inbox',required=True)
    parser.add_argument('--experiment',required=True,help='New ID for every actual experiment')
    parser.add_argument('--watch',action='store_true')
    args = parser.parse_args()
    while True:
        try: print('Exported' if export(args.source,args.inbox,args.experiment) else 'Unchanged',flush=True)
        except (ValueError,OSError) as e:
            if not args.watch: raise
            print('Waiting:',str(e),flush=True)
        if not args.watch: break
        time.sleep(5)


if __name__ == '__main__': main()
