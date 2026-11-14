"""Isolated UI QA server. Never uses the user's Lab data directory."""
import argparse
import json
from pathlib import Path
import uvicorn
from lab.app import create_app
from lab.store import Store
from .test_grouped import snapshot,progress

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,required=True)
    args=parser.parse_args()
    production=Path(__file__).resolve().parent.parent/'data'
    if args.data.resolve()==production.resolve(): raise SystemExit('QA must not use production data')
    store=Store(args.data)
    fixtures=[('partial',snapshot([progress()])),('final',snapshot()),('invalid',snapshot())]
    fixtures[-1][1]['records'][0]['offered']=1
    for state,obj in fixtures:
        obj['metadata']['label']=f'SYNTHETIC UI TEST ONLY — {state}'
        store.ingest(json.dumps(obj).encode(),f'SYNTHETIC-TEST-{state}.json')
    uvicorn.run(create_app(args.data),host='127.0.0.1',port=8766)

if __name__=='__main__': main()
