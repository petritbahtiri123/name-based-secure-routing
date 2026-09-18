import ctypes,hashlib,json,subprocess,shutil,datetime
from pathlib import Path
BASE=Path('C:/NBSR-build').resolve();ROOT=BASE/'etl-compression-b560d0bd'
TARGETS=[BASE/'b4b-task4l-etw-20260905-141214'/n for n in ('kernel.etl','kernel-raw.etl')]+[BASE/'b4b-task4e-20260903-210049'/n for n in ('task4e.etl','task4e-network.etl','task4e-network-raw.etl')]+[BASE/'b4b-task4c-20260903-192550'/n for n in ('task4c.etl','task4c-network.etl','task4c-network-raw.etl')]
kernel=ctypes.WinDLL('kernel32',use_last_error=True);getsize=kernel.GetCompressedFileSizeW;getsize.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)];getsize.restype=ctypes.c_ulong

def allocated(p):
 high=ctypes.c_ulong();ctypes.set_last_error(0);low=getsize(str(p),ctypes.byref(high));error=ctypes.get_last_error()
 if low==0xffffffff and error:raise ctypes.WinError(error)
 return (high.value<<32)|low

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 ROOT.mkdir(exist_ok=False);results=[];initial=shutil.disk_usage(BASE).free
 (ROOT/'policy.json').write_text(json.dumps(dict(operation='lossless per-file NTFS compression; no deletion, move, wildcard, recursive scope or CompactOS',targets=[str(p) for p in TARGETS],preserve='all original paths and logical bytes; SHA256 compared before/after',initial_host_free_bytes=initial),indent=2))
 for i,p in enumerate(TARGETS):
  if shutil.disk_usage(BASE).free>=20*1024**3:break
  resolved=p.resolve(strict=True);assert resolved.is_relative_to(BASE) and resolved==p and p.is_file() and p.suffix.lower()=='.etl'
  stat=p.stat();assert not stat.st_file_attributes & 0x400,'reparse point refused'
  assert not stat.st_file_attributes & 0x4000,'encrypted evidence refused'
  assert (datetime.datetime.now().timestamp()-stat.st_mtime)>86400,'recent file refused'
  if stat.st_file_attributes & 0x800:
   results.append(dict(path=str(p),status='ALREADY_COMPRESSED_SKIPPED'));continue
  print('VERIFY_BEFORE',p.name,flush=True)
  before=digest(p);size_before=allocated(p)
  row=dict(path=str(p),logical_bytes=stat.st_size,sha256_before=before,allocated_bytes_before=size_before,mtime_ns_before=stat.st_mtime_ns)
  (ROOT/f'before-{i}.json').write_text(json.dumps(row,indent=2))
  cmd=['compact.exe','/C','/I','/Q',str(p)];print('COMPRESS',str(p),flush=True)
  q=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
  (ROOT/f'compact-{i}.json').write_text(json.dumps(dict(command=cmd,exit_code=q.returncode,stdout=q.stdout,stderr=q.stderr),indent=2))
  print('VERIFY_AFTER',p.name,flush=True)
  after=digest(p);size_after=allocated(p);new=p.stat()
  row.update(sha256_after=after,allocated_bytes_after=size_after,allocated_bytes_saved=size_before-size_after,logical_bytes_after=new.st_size,mtime_ns_after=new.st_mtime_ns,compact_exit=q.returncode,status='COMPRESSED' if q.returncode==0 and new.st_file_attributes&0x800 else 'NOT_COMPRESSED',hash_unchanged=before==after)
  results.append(row);(ROOT/'results.json').write_text(json.dumps(results,indent=2))
  assert before==after and stat.st_size==new.st_size,'evidence content changed'
  print('UNCHANGED_SHA256_SAVED_BYTES',row['allocated_bytes_saved'],flush=True)
 final=shutil.disk_usage(BASE).free
 (ROOT/'summary.json').write_text(json.dumps(dict(files_processed=len(results),allocated_bytes_saved=sum(x.get('allocated_bytes_saved',0) for x in results),initial_host_free_bytes=initial,final_host_free_bytes=final,observed_host_free_delta=final-initial,all_processed_hashes_unchanged=all(x.get('hash_unchanged',True) for x in results),scope='Storage maintenance only; authoritative ETL logical bytes and paths preserved; observed free-space change may include unrelated background activity'),indent=2))
if __name__=='__main__':main()
