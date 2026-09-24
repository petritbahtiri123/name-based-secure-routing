"""Private stdin/stdout adapter; native peer retains exclusive child ownership."""

import copy
import json
import platform
import queue
import sys
import threading
import time

from scripts.performance import linux_native_peer as native
from scripts.performance.linux_native_duration import bounds
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_loopback import ROOT, write_json
from scripts.performance.linux_native_finite_control import FiniteControl, SCHEMA
from scripts.performance.linux_native_destination_observer import DestinationObserver
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_lifecycle_endpoint import read_commands
from scripts.performance.process_cancellation import Cancellation


def execute_endpoint(args, *, input_stream=None, output_stream=None, delegate=native.execute):
    require(platform.system() == 'Linux', 'Linux required')
    args = copy.copy(args)
    paired = getattr(args, 'paired_live_guards', False)
    require(type(paired) is bool and (not paired or (getattr(args, 'diagnostic_rate', None)
            and getattr(args, 'post_close_reports', False)
            and getattr(args, 'source_live_guard', False) == (args.role == 'source'))), 'invalid paired live mode')
    require(args.ready_input is None and args.phase_control is None, 'endpoint owns readiness; phase observer unsupported')
    output = args.output.resolve()
    require(not args.output.is_symlink() and not output.is_relative_to(ROOT), 'external fresh output required')
    authority = args.authority.resolve()
    require(not output.is_relative_to(authority) and not authority.is_relative_to(output), 'private/output overlap')
    input_stream = input_stream if input_stream is not None else sys.stdin.buffer
    output_stream = output_stream if output_stream is not None else sys.stdout
    output.mkdir(parents=False, exist_ok=False)
    args.output = output / 'peer'
    args.ready_input = output / 'transferred-readiness.json' if args.role == 'source' else None
    stop, messages = threading.Event(), queue.Queue(maxsize=8)
    reader = None
    limits = bounds(getattr(args, 'diagnostic_seconds', None))
    controller_deadline = time.monotonic() + limits['controller_seconds']
    try:
        write_json(output / 'controller.json', dict(schema=SCHEMA, role=args.role,
            paired_live_guards=paired, diagnostic_seconds=getattr(args, 'diagnostic_seconds', None),
            workload=(f"paced diagnostic: 3s warmup/{limits['duration']}s issue"
                      if getattr(args, 'diagnostic_seconds', None) is not None
                      else 'existing finite 3s warmup/20s timed or fixed-work native peer'),
            ownership='owned event proves fresh root, not completed peer preparation',
            ack_scope='Direct peer completion gate' if args.path == 'direct' else 'controller-only; NBSR peer may exit first'))
        # NBSR finite mode already completes after stream ACKs; it does not wait
        # on this Direct-fixture flag. Keep management ACK outside its sealed peer.
        control = FiniteControl(args, ack_path=(output if args.path == 'nbsr' else args.output) / 'completion.ack')
        with (output / 'events.ndjson').open('x', encoding='utf-8', newline='\n') as log:
            def emit(value):
                event = dict(schema=SCHEMA, role=args.role, timestamp_ns=time.monotonic_ns(), **value)
                wire = json.dumps(event, allow_nan=False) + '\n'
                log.write(wire)
                log.flush()
                output_stream.write(wire)
                output_stream.flush()

            reader = threading.Thread(target=read_commands, args=(input_stream, messages, stop), daemon=True)
            reader.start()
            emit(dict(event='owned'))
            received = 0
            destination_observers, pending = [], []
            def destination_factory(root, **kwargs):
                require(not destination_observers, 'duplicate owned destination observer')
                observer = DestinationObserver(root, **kwargs)
                destination_observers.append(observer)
                return observer

            def deliver_pending():
                if destination_observers and destination_observers[0].started:
                    while pending:
                        kind, value, received_ns = pending.pop(0)
                        destination_observers[0].source_event(kind, value, received_ns=received_ns)

            with Cancellation() as cancellation:
                def check():
                    nonlocal received
                    cancellation.check()
                    require(time.monotonic() < controller_deadline, 'finite controller deadline')
                    for event in control.poll():
                        emit(event)
                    deliver_pending()
                    try:
                        wire = messages.get_nowait()
                    except queue.Empty:
                        return
                    if wire is None:
                        raise InterruptedError('control EOF before completion')
                    if isinstance(wire, BaseException):
                        raise wire
                    received += 1
                    require(received <= (limits['progress'] + 3 if paired else 3) and isinstance(wire, bytes) and wire.endswith(b'\n'), 'invalid bounded control frame')
                    value = decode_object(wire)
                    if paired and value.get('op') in ('paced_progress', 'paced_final'):
                        require(args.role == 'destination' and control.ready and set(value) == {'op', 'value'},
                                'invalid destination telemetry request')
                        pending.append((value['op'], value['value'], time.monotonic_ns()))
                        deliver_pending()
                        return
                    if paired and value.get('op') == 'ack':
                        require(destination_observers and destination_observers[0].guard.final is not None
                                and not pending, 'ACK before destination telemetry final')
                    for event in control.request(value):
                        emit(event)

                if args.role == 'source':
                    deadline = time.monotonic() + 30
                    while not control.transferred:
                        check()
                        require(time.monotonic() < deadline, 'readiness transfer deadline')
                        time.sleep(.01)
                extra = {}
                if paired:
                    if args.role == 'source':
                        extra['live_events'] = lambda kind, value: emit(dict(event=kind, value=value))
                    else:
                        extra['destination_observer_factory'] = destination_factory
                outcome = delegate(args, check_cancelled=check, **extra)
                check()
                while args.role == 'destination' and not control.acked:
                    check()
                    time.sleep(.01)
                require(control.transferred if args.role == 'source' else control.acked,
                        'peer completed before control handshake')
                live_result = {}
                if paired and args.role == 'destination':
                    require(destination_observers and destination_observers[0].guard.final is not None,
                            'destination telemetry incomplete')
                    live_result['destination_live_guard'] = destination_observers[0].guard.qualification()
                write_json(output / 'result.json', dict(status='PASS_FINITE_ENDPOINT', role=args.role, **live_result,
                    peer=outcome, sustained_capacity='NOT_ESTABLISHED',
                    runtime_ownership=outcome.get('runtime_ownership_cleanup', 'NOT_MEASURED')))
                emit(dict(event='complete'))
                return outcome
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL', error_type=type(error).__name__, error=str(error)))
        raise
    finally:
        stop.set()
        if reader is not None:
            reader.join(timeout=2)
        seal_output(output)


def main():
    execute_endpoint(native.argument_parser().parse_args())


if __name__ == '__main__':
    main()
