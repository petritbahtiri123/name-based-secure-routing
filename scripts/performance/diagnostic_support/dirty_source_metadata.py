"""Pinned-inventory reporting for an already authenticated /repo source tree.

Callers must supply verified pins and a checked-byte reader. This diagnostic
never grants clean-source acceptance; Git calls remain scoped to /repo.
"""
import hashlib
import json
import subprocess

def dirty_metadata(r, pins, checked_bytes, env):
    # Inputs are the already authenticated manifest inventory, never status paths.
    names=sorted(pins)
    assert 0 < len(names) <= 80, 'metadata inventory bound'
    assert all(len(n)<=240 and not any(x in ('','.','..','00') for x in n.split('/'))
               and not any(x in n.lower() for x in ('private','secret','credential','.pem','.key','.env'))
               and ':' not in n and chr(92) not in n and not n.startswith('/') for n in names), 'metadata path rejected'
    for name in names:
        path=r/name
        assert not any(p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400 for p in (path,*path.parents)), 'metadata alias rejected'
        assert (path.lstat().st_mode & 0o170000)==0o100000, 'metadata regular file required'
    prefix=['git','--no-optional-locks','--literal-pathspecs','-c','safe.directory=',
            '-c','safe.directory=/repo','-C','/repo']
    report={'scope':'pinned source inventory only','files':[],'errors':[]}
    modes={}
    try:
        wire=subprocess.check_output(prefix+['ls-files','--stage','-z','--',*names],cwd=r,env=env,timeout=3)
        assert len(wire)<=32768, 'index metadata bound'
        for record in filter(None,wire.split(b'\0')):
            head,name=record.split(b'\t',1);mode,oid,stage=head.decode('ascii').split();name=name.decode('utf-8')
            assert name in pins and name not in modes and stage=='0' and mode in ('100644','100755'), 'unexpected index entry'
            assert len(oid)==40 and all(c in '0123456789abcdef' for c in oid), 'invalid index object'
            modes[name]=(mode,oid)
        assert set(modes)==set(names), 'index inventory mismatch'
    except Exception as error:report['errors'].append({'operation':'index','type':type(error).__name__});modes={}
    try:
        wire=subprocess.check_output(prefix+['diff','--raw','--no-abbrev','--no-ext-diff','--no-textconv','--no-renames','-z','--',*names],cwd=r,env=env,timeout=3)
        assert len(wire)<=32768, 'raw diff bound'
        # Only raw mode/object/status headers and authenticated inventory paths.
        parts=wire.split(b'\0');rows=[]
        if parts[-1]==b'':parts.pop()
        assert len(parts)%2==0 and len(parts)//2<=80, 'raw record bound'
        for header,path in zip(parts[::2],parts[1::2]):
            values=header.decode('ascii').split();name=path.decode('utf-8')
            assert name in pins and len(values)==5 and values[0].startswith(':'), 'raw record shape'
            assert all(len(x)==6 and all(c in '01234567' for c in x) for x in (values[0][1:],values[1])), 'raw mode'
            assert all(len(x)==40 and all(c in '0123456789abcdef' for c in x) for x in values[2:4]), 'raw object'
            assert values[4] in ('M','A','D','T','U'), 'raw status'
            rows.append({'path':name,'old_mode':values[0][1:],'new_mode':values[1],
                         'old_oid':values[2],'new_oid':values[3],'status':values[4]})
        report['raw_diff']=rows
    except Exception as error:report['errors'].append({'operation':'raw_diff','type':type(error).__name__})
    total=0
    for name in names:
        row={'path':name,'expected_sha256':pins[name]}
        if name in modes:row.update(index_mode=modes[name][0],index_oid=modes[name][1])
        try:
            path=r/name
            assert not any(p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400 for p in (path,*path.parents)), 'alias rejected'
            st=path.lstat();assert (st.st_mode & 0o170000)==0o100000, 'regular file required'
            total+=st.st_size;assert st.st_size<=4*1024**2 and total<=16*1024**2, 'hash byte bound'
            value=checked_bytes(path);assert len(value)==st.st_size, 'size changed'
            actual=hashlib.sha256(value).hexdigest()
            row.update(lstat_mode=oct(st.st_mode),size=st.st_size,actual_sha256=actual,bytes_match=actual==pins[name],
                       git_worktree_mode='100755' if st.st_mode & 0o100 else '100644')
        except Exception as error:row['error']=type(error).__name__
        report['files'].append(row)
    return report

def require_clean_status(status, metadata=None):
    if status:
        report={'bytes':len(status),'sha256':hashlib.sha256(status).hexdigest(),
                'status_preview_omitted':'paths emitted only from authenticated pinned metadata inventory'}
        if metadata is not None:report['metadata']=metadata
        raise AssertionError('working tree not clean: '+json.dumps(report,ensure_ascii=True))
