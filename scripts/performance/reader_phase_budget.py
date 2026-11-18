"""Historical150MiB phase arithmetic. Pure accounting, never live authority.

Requires full exact snapshots and the admitted frozen allocation; defaults preserve
RUN1709 historical limits, not permission to use them for another campaign.
"""


def project(counts, normal, cleanup, used, auxiliary_used, *, aux_cap, cleanup_cap=2097152, output_cap=157286400):
    def number(v):
        if type(v) is not int or v < 0:
            raise ValueError("nonnegative exact byte count required")
        return v

    if set(normal) & set(cleanup):
        raise ValueError("overlapping phase slots")
    for k in ("task", "output", "artifacts"):
        number(counts.get(k))
    for v in [*normal.values(), *cleanup.values(), *used.values(), auxiliary_used, aux_cap, cleanup_cap, output_cap]:
        number(v)
    slots = dict(normal, **cleanup)
    if any(k not in slots or v > slots[k] for k, v in used.items()):
        raise ValueError("unallocated or overfull slot")
    if sum(cleanup.values()) > cleanup_cap or auxiliary_used > aux_cap:
        raise ValueError("phase partition overflow")
    nr = sum(normal.values()) - sum(used.get(k, 0) for k in normal)
    cr = cleanup_cap - sum(used.get(k, 0) for k in cleanup)
    ar = aux_cap - auxiliary_used
    remaining = nr + cr + ar
    if counts["output"] + remaining > output_cap:
        raise ValueError("150MiB actual plus remaining obligations")
    if counts["task"] + remaining > min(7 * 1024**3, 6739946464 + 378 * 1024**2) or counts["artifacts"] + remaining > 7 * 1024**3:
        raise ValueError("global remaining obligations")
    return dict(
        remaining_normal=nr,
        remaining_cleanup=cr,
        remaining_auxiliary=ar,
        remaining_total=remaining,
        projected_output=counts["output"] + remaining,
        projected_task=counts["task"] + remaining,
    )


def align(counts, scanned_root):
    old = counts.get("phase_root")
    if type(old) is not int or old < 0 or type(scanned_root) is not int or scanned_root < 0:
        raise ValueError("coherent current-root snapshot required")
    result = dict(counts)
    for key in ("task", "artifacts", "output"):
        value = counts.get(key)
        if type(value) is not int or value < old:
            raise ValueError("current-root contribution exceeds group")
        result[key] = value - old + scanned_root
    result["phase_root"] = scanned_root
    return result
