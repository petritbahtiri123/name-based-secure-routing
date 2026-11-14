"""Read-only marker inventory; never infers process ownership or readiness."""
from .setup import private_path

MARKERS = {
    'dashboard': 'tools/demo-lab/.state/ui.lock',
    'unresolved_run': 'tools/demo-lab/.state/active.json',
    'historical_demo': 'client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/active.lock',
}


def inspect(repo):
    markers = {}
    for name, relative in MARKERS.items():
        try:
            path = private_path(repo / relative)
            path.lstat()
        except FileNotFoundError:
            markers[name] = 'ABSENT'
        except (OSError, ValueError):
            markers[name] = 'UNKNOWN'
        else:
            markers[name] = 'PRESENT'
    return {
        'markers': markers,
        'reconciliation_required': any(value != 'ABSENT' for value in markers.values()),
        'readiness': 'NOT_ESTABLISHED',
        'validation': 'Read-only marker snapshot, not process liveness, ownership, cleanup or runtime acceptance. '
                      'Absence does not establish that no workload exists. Concurrent state may change.',
        'next': 'For PRESENT or UNKNOWN, reconcile exact owner/process identities and receipts before restart; '
                'never delete a lock or replay a request based on this report.',
        'platform_scope': 'Windows local demo evidence only; Mac host / Linux container prepared but UNTESTED; '
                          'compatibility unknown. No clean-machine or production-readiness claim.',
    }
