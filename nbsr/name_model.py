import re


HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def normalize_hostname(value: str) -> str:
    hostname = value.rstrip(".").lower()
    if not hostname or len(hostname) > 253 or ".." in hostname:
        raise ValueError("Invalid NBSR hostname")
    labels = hostname.split(".")
    if any(not HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("Invalid NBSR hostname")
    return hostname
