"""Sign only existing public CSR files. CA private material never serialized."""
import pathlib,sys,json,hashlib
from tls_roles import sign_public
if __name__=='__main__':
    root=pathlib.Path(sys.argv[1]);out=root/'certificates';out.mkdir(exist_ok=False)
    for name,b in sign_public({r:(root/(r+'.csr')).read_bytes() for r in ['source','destination']}).items():
        (out/name).write_bytes(b)

    (out/'public-hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.der')},sort_keys=True))
