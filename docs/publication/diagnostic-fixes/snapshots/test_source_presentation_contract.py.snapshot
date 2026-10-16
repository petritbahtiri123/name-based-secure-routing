import hashlib,io,tarfile,unittest
from source_presentation_contract import verify_archive
class Contract(unittest.TestCase):
 def fixture(self,name='src/a.py',mode=0o644,body=b'public',kind=tarfile.REGTYPE,duplicate=False):
  output=io.BytesIO()
  with tarfile.open(fileobj=output,mode='w') as archive:
   for _ in range(2 if duplicate else 1):
    entry=tarfile.TarInfo(name);entry.mode=mode;entry.size=len(body) if kind==tarfile.REGTYPE else 0;entry.type=kind
    if kind==tarfile.SYMTYPE:entry.linkname='/private/key'
    archive.addfile(entry,io.BytesIO(body) if kind==tarfile.REGTYPE else None)
  return output.getvalue()
 def pins(self,name='src/a.py'):return {name:dict(mode=0o644,size=6,sha256=hashlib.sha256(b'public').hexdigest())}
 def test_exact_bytes_modes(self):self.assertEqual(verify_archive(self.fixture(),self.pins())['files'],1)
 def test_mode_drift_rejected(self):
  with self.assertRaises(ValueError):verify_archive(self.fixture(mode=0o755),self.pins())
 def test_byte_drift_rejected(self):
  with self.assertRaises(ValueError):verify_archive(self.fixture(body=b'change'),self.pins())
 def test_alias_git_and_symlink_rejected(self):
  for name in ['../a','/a','.git/config','src/../a']:
   with self.assertRaises(ValueError):verify_archive(self.fixture(name=name),self.pins(name))
  with self.assertRaises(ValueError):verify_archive(self.fixture(kind=tarfile.SYMTYPE),self.pins())
 def test_duplicate_rejected(self):
  with self.assertRaises(ValueError):verify_archive(self.fixture(duplicate=True),self.pins())
if __name__=='__main__':unittest.main()
