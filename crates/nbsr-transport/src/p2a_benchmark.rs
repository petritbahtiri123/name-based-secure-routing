//! Benchmark-only P2A application framing. Not an NBSR wire protocol.

use sha2::{Digest, Sha256};

const HEADER_BYTES: usize = 12;
const TAG_BYTES: usize = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameError {
    Truncated,
    WrongSequence,
    WrongLength,
    Corrupt,
}

pub fn encode_frame(sequence: u64, payload: &[u8]) -> Vec<u8> {
    let mut wire = Vec::with_capacity(HEADER_BYTES + payload.len() + TAG_BYTES);
    wire.extend_from_slice(&sequence.to_be_bytes());
    wire.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    wire.extend_from_slice(payload);
    let tag = Sha256::digest(&wire);
    wire.extend_from_slice(&tag[..TAG_BYTES]);
    wire
}

pub fn decode_frame(
    wire: &[u8],
    expected_sequence: u64,
    expected_payload_bytes: usize,
) -> Result<Vec<u8>, FrameError> {
    if wire.len() < HEADER_BYTES + TAG_BYTES {
        return Err(FrameError::Truncated);
    }
    let sequence = u64::from_be_bytes(wire[..8].try_into().unwrap());
    if sequence != expected_sequence {
        return Err(FrameError::WrongSequence);
    }
    let payload_bytes = u32::from_be_bytes(wire[8..12].try_into().unwrap()) as usize;
    if payload_bytes != expected_payload_bytes
        || wire.len() != HEADER_BYTES + payload_bytes + TAG_BYTES
    {
        return Err(FrameError::WrongLength);
    }
    let tag_at = HEADER_BYTES + payload_bytes;
    let expected_tag = Sha256::digest(&wire[..tag_at]);
    if wire[tag_at..] != expected_tag[..TAG_BYTES] {
        return Err(FrameError::Corrupt);
    }
    Ok(wire[HEADER_BYTES..tag_at].to_vec())
}
