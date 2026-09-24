"""Declared sequential diagnostic workload bounds; transport timers are unchanged."""

from scripts.performance.linux_b5_ceiling import require

CYCLE_COUNTS = (1, 2, 4, 8, 10, 16, 25, 50, 100)


def cycle_bounds(cycles):
    require(type(cycles) is int and cycles in CYCLE_COUNTS, 'invalid cycle count')
    return dict(controller_seconds=120 if cycles <= 16 else 120 + cycles * 4)


def stream_count(value):
    require(type(value) is int and 1 <= value <= 64, 'invalid streams per channel')
    return value


def validate_active_shape(value, streams):
    stream_count(streams)
    require(value.get('phase') == 'b3_materialized_streams_ready', 'materialized phase required')
    expected = dict(transport_sessions_current_live=1, service_channels_current_live=1,
                    application_streams_current_live=streams, quic_streams_current_live=streams)
    require(all(type(value.get(key)) is int and value[key] == count for key, count in expected.items()),
            'materialized stream ownership cardinality mismatch')
