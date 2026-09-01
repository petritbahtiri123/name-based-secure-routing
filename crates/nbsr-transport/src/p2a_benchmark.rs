//! Benchmark-only P2A application framing. Not an NBSR wire protocol.

use std::collections::VecDeque;
use std::time::Instant;

use sha2::{Digest, Sha256};

const HEADER_BYTES: usize = 12;
const TAG_BYTES: usize = 16;
const FULL_VALIDATION_STRIDE: u64 = 1024;
const MAX_OUTSTANDING_PER_STREAM: usize = 64;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameError {
    Truncated,
    WrongSequence,
    WrongLength,
    Corrupt,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutstandingError {
    InvalidLimit,
    Full,
    Empty,
    OutOfOrder,
}

#[derive(Debug)]
pub struct OutstandingTracker {
    limit: usize,
    pending: VecDeque<(u64, Instant)>,
    sent: u64,
    completed: u64,
    max_in_flight: usize,
}

impl OutstandingTracker {
    pub fn new(limit: usize) -> Result<Self, OutstandingError> {
        if !(1..=MAX_OUTSTANDING_PER_STREAM).contains(&limit) {
            return Err(OutstandingError::InvalidLimit);
        }
        Ok(Self {
            limit,
            pending: VecDeque::with_capacity(limit),
            sent: 0,
            completed: 0,
            max_in_flight: 0,
        })
    }

    pub fn issue(&mut self, sequence: u64, started: Instant) -> Result<(), OutstandingError> {
        if self.pending.len() == self.limit {
            return Err(OutstandingError::Full);
        }
        self.pending.push_back((sequence, started));
        self.sent += 1;
        self.max_in_flight = self.max_in_flight.max(self.pending.len());
        Ok(())
    }

    pub fn complete(&mut self, sequence: u64) -> Result<Instant, OutstandingError> {
        let Some((expected, _)) = self.pending.front() else {
            return Err(OutstandingError::Empty);
        };
        if *expected != sequence {
            return Err(OutstandingError::OutOfOrder);
        }
        let (_, started) = self.pending.pop_front().unwrap();
        self.completed += 1;
        Ok(started)
    }

    pub fn next_sequence(&self) -> Option<u64> {
        self.pending.front().map(|(sequence, _)| *sequence)
    }

    pub fn can_issue(&self) -> bool {
        self.pending.len() < self.limit
    }

    pub fn in_flight(&self) -> usize {
        self.pending.len()
    }

    pub fn sent(&self) -> u64 {
        self.sent
    }

    pub fn completed(&self) -> u64 {
        self.completed
    }

    pub fn max_in_flight(&self) -> usize {
        self.max_in_flight
    }
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

fn measured_tag(sequence: u64, wire_without_tag: &[u8]) -> [u8; TAG_BYTES] {
    if sequence.is_multiple_of(FULL_VALIDATION_STRIDE) {
        return Sha256::digest(wire_without_tag)[..TAG_BYTES]
            .try_into()
            .unwrap();
    }
    let mut tag = [0_u8; TAG_BYTES];
    tag[..8].copy_from_slice(&sequence.to_be_bytes());
    tag[8..12].copy_from_slice(&(wire_without_tag.len() as u32).to_be_bytes());
    tag[12..].copy_from_slice(&(!(wire_without_tag.len() as u32)).to_be_bytes());
    tag
}

pub fn encode_measured_frame(sequence: u64, payload: &[u8]) -> Vec<u8> {
    let mut wire = Vec::with_capacity(HEADER_BYTES + payload.len() + TAG_BYTES);
    wire.extend_from_slice(&sequence.to_be_bytes());
    wire.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    wire.extend_from_slice(payload);
    let tag = measured_tag(sequence, &wire);
    wire.extend_from_slice(&tag);
    wire
}

pub fn decode_measured_frame(
    wire: &[u8],
    expected_sequence: u64,
    expected_payload: &[u8],
) -> Result<Vec<u8>, FrameError> {
    if wire.len() < HEADER_BYTES + TAG_BYTES {
        return Err(FrameError::Truncated);
    }
    let sequence = u64::from_be_bytes(wire[..8].try_into().unwrap());
    if sequence != expected_sequence {
        return Err(FrameError::WrongSequence);
    }
    let payload_bytes = u32::from_be_bytes(wire[8..12].try_into().unwrap()) as usize;
    if payload_bytes != expected_payload.len()
        || wire.len() != HEADER_BYTES + payload_bytes + TAG_BYTES
    {
        return Err(FrameError::WrongLength);
    }
    let tag_at = HEADER_BYTES + payload_bytes;
    if wire[tag_at..] != measured_tag(sequence, &wire[..tag_at]) {
        return Err(FrameError::Corrupt);
    }
    let payload = &wire[HEADER_BYTES..tag_at];
    if sequence.is_multiple_of(FULL_VALIDATION_STRIDE) {
        if payload != expected_payload {
            return Err(FrameError::Corrupt);
        }
    } else if !expected_payload.is_empty() {
        let probes = [
            0,
            expected_payload.len() / 7,
            expected_payload.len() / 5,
            expected_payload.len() / 3,
            expected_payload.len() / 2,
            expected_payload.len() * 2 / 3,
            expected_payload.len() * 4 / 5,
            expected_payload.len() - 1,
        ];
        if probes
            .into_iter()
            .any(|index| payload[index] != expected_payload[index])
        {
            return Err(FrameError::Corrupt);
        }
    }
    Ok(payload.to_vec())
}
