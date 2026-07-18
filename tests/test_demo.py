from base64 import urlsafe_b64decode

from scripts.demo import tamper_ticket


def decode_segment(segment: str) -> bytes:
    return urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_tamper_ticket_changes_decoded_signature_bytes():
    signature = "A" * 86
    ticket = f"header.payload.{signature}"

    tampered = tamper_ticket(ticket)
    original_parts = ticket.split(".")
    tampered_parts = tampered.split(".")

    assert tampered_parts[:2] == original_parts[:2]
    assert decode_segment(tampered_parts[2]) != decode_segment(original_parts[2])
