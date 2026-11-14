"""Bounded artifact format dispatch. Original bytes always stay in the store."""
import json
import re
from .adapters import decode, normalize, MAX_BYTES
from .grouped import normalize_grouped, ENVELOPE, PROGRESS_SCHEMA, FINAL_SCHEMA


def normalize_artifact(raw):
    if len(raw)>MAX_BYTES: raise ValueError('Artifact exceeds 4 MiB limit')
    try:
        obj=decode(raw)
    except ValueError as initial:
        lines=raw.splitlines(keepends=True)
        if len(lines)<2: raise initial
        if len(lines)>4096: raise ValueError('NDJSON exceeds 4096 lines')
        records=[]; numbers=[]; truncated=False
        for n,line in enumerate(lines,1):
            if not line.strip(): continue
            if len(line)>65536: raise ValueError('NDJSON line exceeds 64 KiB')
            try: row=decode(line)
            except ValueError as error:
                # A final cut-off line is expected for an explicit progress snapshot.
                # Only accept it after a complete known progress record; raw bytes remain.
                cause=error.__cause__
                incomplete=isinstance(cause,json.JSONDecodeError) and (
                    cause.pos>=len(cause.doc.rstrip()) or cause.msg.startswith('Unterminated string') or
                    (cause.msg=="Expecting ',' delimiter" and bool(re.fullmatch(r'(?:[eE][+-]?|\.)',cause.doc[cause.pos:]))))
                if incomplete and n==len(lines) and not line.endswith(b'\n') and records and any(r.get('schema')==PROGRESS_SCHEMA for r in records):
                    truncated=True; break
                raise ValueError(f'Invalid NDJSON record at line {n}')
            records.append(row); numbers.append(n)
        return normalize_grouped(records,truncated_tail=truncated,record_numbers=numbers)
    if obj.get('schema')==ENVELOPE:
        if set(obj)-{'schema','metadata','records'}: raise ValueError('Unsupported snapshot envelope fields')
        return normalize_grouped(obj.get('records'),obj.get('metadata'))
    if obj.get('schema') in (PROGRESS_SCHEMA,FINAL_SCHEMA):
        return normalize_grouped([obj])
    return normalize(obj)
