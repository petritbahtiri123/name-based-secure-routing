#!/usr/bin/env python3
"""Repository-local entry point; no import-time installation or listeners."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description='NBSR local Demo Lab (not a benchmark controller)')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('check', help='Read-only prerequisites and source inspection')
    prepare = commands.add_parser('prepare', help='Show dependency plan; downloads are explicit')
    prepare.add_argument('--allow-downloads', action='store_true')
    commands.add_parser('build', help='Bounded offline source build, no demo execution')
    serve = commands.add_parser('serve', help='Open authenticated loopback dashboard')
    serve.add_argument('--no-browser', action='store_true')
    verify = commands.add_parser('verify', help='Verify retained evidence without server or network')
    verify.add_argument('--run-id', required=True)
    worker = commands.add_parser('_worker', help=argparse.SUPPRESS)
    worker.add_argument('--request', required=True)
    image = commands.add_parser('configure-image', help='Select a reviewed local Mac/Linux image identity; no pull or execution')
    image.add_argument('--image-id', required=True)
    container = commands.add_parser('_container-worker', help=argparse.SUPPRESS)
    container.add_argument('--scenario', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    state = repo / 'tools/demo-lab/.state'
    from nbsr_demo_lab import setup
    try:
        if args.action == 'check':
            result = setup.check(repo)
            print(json.dumps(result, indent=2))
            return 0 if result['ready_for_build'] else 2
        if args.action == 'prepare':
            result = setup.prepare(repo, state, allow_downloads=args.allow_downloads)
            print(json.dumps(result, indent=2))
            return 2 if result.get('ready_for_build') is False else 0
        elif args.action == 'build':
            print(json.dumps(setup.build(repo, state), indent=2))
        elif args.action == 'verify':
            if not re.fullmatch(r'demo-[0-9a-f]{32}', args.run_id):
                raise ValueError('Run ID must be the exact ID printed by Demo Lab')
            from nbsr_demo_lab.evidence import verify
            result = verify(state / 'runs' / args.run_id)
            print(json.dumps(result, indent=2))
            return 0 if result['valid'] and result['outcome'] == 'PASS' else 1
        elif args.action == '_worker':
            from nbsr_demo_lab.worker import run
            run(args.request)
        elif args.action == 'configure-image':
            from nbsr_demo_lab.mac import configure
            print(json.dumps(configure(state, args.image_id), indent=2))
        elif args.action == '_container-worker':
            from nbsr_demo_lab.mac import container_worker
            return container_worker(args.scenario)
        elif args.action == 'serve':
            from nbsr_demo_lab.coordinator import Coordinator
            from nbsr_demo_lab.web import serve
            setup.private_path(state)
            state.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = state / 'ui.lock'
            # Never silently remove a lock after crash; owner must reconcile first.
            with lock.open('x', encoding='utf-8') as file:
                import os
                file.write(json.dumps({'pid': os.getpid(), 'purpose': 'demo-ui'}))
            try:
                serve(Coordinator(repo, state), open_browser=not args.no_browser)
            finally:
                lock.unlink()
        return 0
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
        print(f'Demo Lab stopped: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
