from pathlib import Path
import hashlib,io,json,subprocess,tarfile
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.linux_b5_placement import seal_output
r=Path('C:/NBSR-build/native-bind-metadata-20260925');r.mkdir()
rows=[]
for name,label in [('native-streams-b9a29408','streams16-r1'),('native-channels-09b36ece','channels16-r1'),('native-memory-04866375','c1-s1-r1'),('native-memory50-04866375','c1-s1-r1')]:
 root=Path('C:/NBSR-build')/name
 verify_index(root)
 saved=json.loads((root/(label+'-containers-after.json')).read_bytes())
 config=json.loads((root/label/'config.json').read_bytes())
 build=Path('C:/NBSR-build')/('linux-current-'+config['source_sha'][:8])
 for container,prior in saved.items():
  current=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
  assert current['Id']==prior['Id'] and current['State']['Status']=='exited'
  files={}
  for name2 in ('source-sha.txt','build-manifest.json','update.bundle'):
   wire=subprocess.check_output(['docker','cp',container+':/build/'+name2,'-'])
   with tarfile.open(fileobj=io.BytesIO(wire)) as tar:
    entries=[m for m in tar.getmembers() if m.isfile()]
    assert len(entries)==1
    data=tar.extractfile(entries[0]).read()
   expected=(build/name2).read_bytes()
   assert data==expected
   files[name2]=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),matches_host_build=True)
  rows.append(dict(container=container,id=current['Id'],expected_source_sha=config['source_sha'],actual_build=str(build),
    inspect_build_mount=[m for m in current['Mounts'] if m['Destination']=='/build'],files=files))
image=json.loads(subprocess.check_output(['docker','image','inspect','nbsr-native-prepared-cache:a401567d']))[0]
labels={k:v for k,v in (image['Config'].get('Labels') or {}).items() if k.startswith('desktop.docker.io/binds/')}
(r/'result.json').write_text(json.dumps(dict(status='ACTUAL_BUILD_BYTES_MATCH',rows=rows,image_id=image['Id'],inherited_desktop_bind_labels=labels,
 classification='DIAGNOSTIC_METADATA_REPORTING_ARTIFACT',mechanism='NOT_PROVEN; direct read matches requested build despite stale inspect source path'),indent=2),encoding='utf-8')
seal_output(r)
print('ACTUAL_BUILD_BYTES_MATCH',len(rows),'containers',sum(len(x['files']) for x in rows),'files')
