import argparse
from pathlib import Path
from .store import Store

def main():
    parser = argparse.ArgumentParser(description='Import a reviewed local JSON artifact. Does not execute benchmarks.')
    parser.add_argument('files',nargs='+',type=Path)
    parser.add_argument('--data',type=Path,default=Path(__file__).resolve().parent.parent/'data')
    args = parser.parse_args()
    store = Store(args.data)
    for path in args.files: print(path.name,store.ingest(path.read_bytes(),path.name))

if __name__ == '__main__': main()
