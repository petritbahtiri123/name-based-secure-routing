"""Private sequential-cycle endpoint; no sustainable admission or memory-cost claim."""

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_endpoint as endpoint
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_control import CycleBarrier, decode_control, decode_object


def decode_cycle_control(wire):
    value = decode_object(wire)
    if value.get('op') in ('readiness', 'cancel'):
        return decode_control(wire)
    require(set(value) == {'op', 'cycle'} and value['op'] in ('start', 'release', 'final_release')
            and type(value['cycle']) is int and 0 <= value['cycle'] < 16, 'invalid cycle control')
    return value


class CycleEndpointControl(endpoint.EndpointControl):
    def __init__(self, args, output, *, capture=None):
        self.args = args
        self.prepared = self.ready_sent = self.transferred = False
        self.barrier = CycleBarrier(role=args.role, cycles=args.cycles, root=args.lifecycle,
            output=output, capture=capture or self.capture)

    def request(self, message):
        if message['op'] in ('readiness', 'cancel'):
            return super().request(message)
        require(self.transferred if self.args.role == 'source' else self.ready_sent,
                'readiness required before cycle control')
        return self.barrier.request(message['op'], message['cycle'])


def execute_endpoint(args, **kwargs):
    return endpoint.execute_endpoint(args, control_factory=CycleEndpointControl,
                                     decoder=decode_cycle_control, **kwargs)


def argument_parser():
    return native.argument_parser(sequential=True)


def main():
    execute_endpoint(argument_parser().parse_args())


if __name__ == '__main__':
    main()
