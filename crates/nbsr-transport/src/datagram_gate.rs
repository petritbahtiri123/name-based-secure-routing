//! Quinn-free Core v0.2 UDP DATAGRAM framing and bounded channel state.

use std::collections::VecDeque;
use std::fmt;

pub const MAX_DATAGRAM_PAYLOAD: usize = 1_200;
const MAX_QUEUED_DATAGRAMS: usize = 64;
const TOKEN_CAPACITY_MILLIS: u64 = 200_000;
const TOKEN_COST_MILLIS: u64 = 1_000;
const TOKEN_REFILL_PER_MILLISECOND: u64 = 100;

#[derive(Clone, Eq, PartialEq)]
pub struct DatagramFrame {
    channel_id: [u8; 16],
    sequence: u64,
    payload: Vec<u8>,
}

impl DatagramFrame {
    pub fn new(
        channel_id: [u8; 16],
        sequence: u64,
        payload: Vec<u8>,
    ) -> Result<Self, DatagramReject> {
        if channel_id == [0; 16] || sequence == 0 {
            return Err(DatagramReject::InvalidFrame);
        }
        if payload.len() > MAX_DATAGRAM_PAYLOAD {
            return Err(DatagramReject::PayloadTooLarge);
        }
        Ok(Self {
            channel_id,
            sequence,
            payload,
        })
    }

    pub fn channel_id(&self) -> [u8; 16] {
        self.channel_id
    }

    pub fn sequence(&self) -> u64 {
        self.sequence
    }

    pub fn payload(&self) -> &[u8] {
        &self.payload
    }
}

impl fmt::Debug for DatagramFrame {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("DatagramFrame")
            .field("channel_id", &self.channel_id)
            .field("sequence", &self.sequence)
            .field("payload_len", &self.payload.len())
            .finish()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DatagramReject {
    AuditUnavailable,
    BackwardsTime,
    ConnectionMismatch,
    InvalidFrame,
    InvalidState,
    PayloadTooLarge,
    PeerMaximum,
    QueueFull,
    RateLimited,
    Replay,
    SequenceExhausted,
    TransportFailed,
    WrongChannel,
}

impl fmt::Display for DatagramReject {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::AuditUnavailable => "datagram audit unavailable",
            Self::BackwardsTime => "datagram clock moved backwards",
            Self::ConnectionMismatch => "datagram connection mismatch",
            Self::InvalidFrame => "invalid datagram frame",
            Self::InvalidState => "datagram channel is not active",
            Self::PayloadTooLarge => "datagram payload exceeds the profile bound",
            Self::PeerMaximum => "datagram exceeds the negotiated peer maximum",
            Self::QueueFull => "datagram receive queue is full",
            Self::RateLimited => "datagram rate limit exceeded",
            Self::Replay => "datagram sequence rejected",
            Self::SequenceExhausted => "datagram sequence exhausted",
            Self::TransportFailed => "datagram transport failed",
            Self::WrongChannel => "datagram channel mismatch",
        })
    }
}

impl std::error::Error for DatagramReject {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum DatagramDropReason {
    BackwardsTime,
    InvalidState,
    Oversize,
    QueueFull,
    RateLimit,
    Replay,
    SequenceExhausted,
    WrongChannel,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum DatagramAuditMutation {
    Send,
    Receive,
    Pop,
    Drop(DatagramDropReason),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DatagramReceive {
    Queued,
    DroppedQueueFull,
}

pub(crate) struct DatagramGate {
    active: bool,
    channel_id: [u8; 16],
    highest_inbound: u64,
    inbound_bucket: TokenBucket,
    next_outbound: Option<u64>,
    outbound_bucket: TokenBucket,
    queue: VecDeque<Vec<u8>>,
}

impl fmt::Debug for DatagramGate {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("DatagramGate")
            .field("active", &self.active)
            .field("channel_id", &self.channel_id)
            .field("highest_inbound", &self.highest_inbound)
            .field("next_outbound", &self.next_outbound)
            .field("queued", &self.queue.len())
            .finish()
    }
}

impl DatagramGate {
    pub(crate) fn new(channel_id: [u8; 16]) -> Self {
        Self {
            active: channel_id != [0; 16],
            channel_id,
            highest_inbound: 0,
            inbound_bucket: TokenBucket::new(),
            next_outbound: Some(1),
            outbound_bucket: TokenBucket::new(),
            queue: VecDeque::with_capacity(MAX_QUEUED_DATAGRAMS),
        }
    }

    #[cfg(test)]
    fn queued(&self) -> usize {
        self.queue.len()
    }

    pub(crate) fn payload_capacity(&self, peer_maximum: usize) -> Result<usize, DatagramReject> {
        if !self.active {
            return Err(DatagramReject::InvalidState);
        }
        let sequence = self
            .next_outbound
            .ok_or(DatagramReject::SequenceExhausted)?;
        max_datagram_payload(peer_maximum, self.channel_id, sequence)
            .ok_or(DatagramReject::PeerMaximum)
    }

    pub(crate) fn send<F>(
        &mut self,
        payload: &[u8],
        peer_maximum: usize,
        monotonic_milliseconds: u64,
        reserve_audit: F,
    ) -> Result<Vec<u8>, DatagramReject>
    where
        F: FnOnce(DatagramAuditMutation) -> Result<(), ()>,
    {
        if !self.active {
            return Err(DatagramReject::InvalidState);
        }
        let Some(sequence) = self.next_outbound else {
            reserve_audit(DatagramAuditMutation::Drop(
                DatagramDropReason::SequenceExhausted,
            ))
            .map_err(|_| DatagramReject::AuditUnavailable)?;
            return Err(DatagramReject::SequenceExhausted);
        };
        let encoded = match encode_datagram_frame(self.channel_id, sequence, payload, peer_maximum)
        {
            Ok(encoded) => encoded,
            Err(error @ (DatagramReject::PayloadTooLarge | DatagramReject::PeerMaximum)) => {
                reserve_audit(DatagramAuditMutation::Drop(DatagramDropReason::Oversize))
                    .map_err(|_| DatagramReject::AuditUnavailable)?;
                return Err(error);
            }
            Err(error) => return Err(error),
        };
        let prepared = match self.outbound_bucket.prepare(monotonic_milliseconds) {
            Ok(prepared) => prepared,
            Err(error) => {
                let reason = match error {
                    DatagramReject::BackwardsTime => DatagramDropReason::BackwardsTime,
                    DatagramReject::RateLimited => DatagramDropReason::RateLimit,
                    _ => DatagramDropReason::InvalidState,
                };
                reserve_audit(DatagramAuditMutation::Drop(reason))
                    .map_err(|_| DatagramReject::AuditUnavailable)?;
                return Err(error);
            }
        };
        reserve_audit(DatagramAuditMutation::Send).map_err(|_| DatagramReject::AuditUnavailable)?;
        self.outbound_bucket.commit(prepared);
        self.next_outbound = sequence.checked_add(1);
        Ok(encoded)
    }

    pub(crate) fn receive<F>(
        &mut self,
        frame: DatagramFrame,
        monotonic_milliseconds: u64,
        reserve_audit: F,
    ) -> Result<DatagramReceive, DatagramReject>
    where
        F: FnOnce(DatagramAuditMutation) -> Result<(), ()>,
    {
        if frame.channel_id != self.channel_id {
            reserve_audit(DatagramAuditMutation::Drop(
                DatagramDropReason::WrongChannel,
            ))
            .map_err(|_| DatagramReject::AuditUnavailable)?;
            return Err(DatagramReject::WrongChannel);
        }
        if frame.sequence <= self.highest_inbound {
            reserve_audit(DatagramAuditMutation::Drop(DatagramDropReason::Replay))
                .map_err(|_| DatagramReject::AuditUnavailable)?;
            return Err(DatagramReject::Replay);
        }
        if !self.active {
            return Err(DatagramReject::InvalidState);
        }
        let prepared = match self.inbound_bucket.prepare(monotonic_milliseconds) {
            Ok(prepared) => prepared,
            Err(error) => {
                let reason = match error {
                    DatagramReject::BackwardsTime => DatagramDropReason::BackwardsTime,
                    DatagramReject::RateLimited => DatagramDropReason::RateLimit,
                    _ => DatagramDropReason::InvalidState,
                };
                reserve_audit(DatagramAuditMutation::Drop(reason))
                    .map_err(|_| DatagramReject::AuditUnavailable)?;
                return Err(error);
            }
        };
        if self.queue.len() >= MAX_QUEUED_DATAGRAMS {
            reserve_audit(DatagramAuditMutation::Drop(DatagramDropReason::QueueFull))
                .map_err(|_| DatagramReject::AuditUnavailable)?;
            self.highest_inbound = frame.sequence;
            return Ok(DatagramReceive::DroppedQueueFull);
        }
        reserve_audit(DatagramAuditMutation::Receive)
            .map_err(|_| DatagramReject::AuditUnavailable)?;
        self.inbound_bucket.commit(prepared);
        self.highest_inbound = frame.sequence;
        self.queue.push_back(frame.payload);
        Ok(DatagramReceive::Queued)
    }

    pub(crate) fn pop<F>(&mut self, reserve_audit: F) -> Result<Option<Vec<u8>>, DatagramReject>
    where
        F: FnOnce(DatagramAuditMutation) -> Result<(), ()>,
    {
        if !self.active {
            return Err(DatagramReject::InvalidState);
        }
        if self.queue.is_empty() {
            return Ok(None);
        }
        reserve_audit(DatagramAuditMutation::Pop).map_err(|_| DatagramReject::AuditUnavailable)?;
        Ok(self.queue.pop_front())
    }

    pub(crate) fn deactivate(&mut self) {
        self.active = false;
        self.next_outbound = None;
        self.inbound_bucket.clear();
        self.outbound_bucket.clear();
        self.queue.clear();
    }
}

struct TokenBucket {
    last_milliseconds: Option<u64>,
    token_millis: u64,
}

#[derive(Clone, Copy)]
struct PreparedBucket {
    last_milliseconds: u64,
    token_millis: u64,
}

impl TokenBucket {
    fn new() -> Self {
        Self {
            last_milliseconds: None,
            token_millis: TOKEN_CAPACITY_MILLIS,
        }
    }

    fn prepare(&self, now: u64) -> Result<PreparedBucket, DatagramReject> {
        let token_millis = match self.last_milliseconds {
            None => self.token_millis,
            Some(last) if now < last => return Err(DatagramReject::BackwardsTime),
            Some(last) => {
                let elapsed = now - last;
                if elapsed >= 2_000 {
                    TOKEN_CAPACITY_MILLIS
                } else {
                    self.token_millis
                        .checked_add(
                            elapsed
                                .checked_mul(TOKEN_REFILL_PER_MILLISECOND)
                                .ok_or(DatagramReject::BackwardsTime)?,
                        )
                        .ok_or(DatagramReject::BackwardsTime)?
                        .min(TOKEN_CAPACITY_MILLIS)
                }
            }
        };
        if token_millis < TOKEN_COST_MILLIS {
            return Err(DatagramReject::RateLimited);
        }
        Ok(PreparedBucket {
            last_milliseconds: now,
            token_millis: token_millis - TOKEN_COST_MILLIS,
        })
    }

    fn commit(&mut self, prepared: PreparedBucket) {
        self.last_milliseconds = Some(prepared.last_milliseconds);
        self.token_millis = prepared.token_millis;
    }

    fn clear(&mut self) {
        self.last_milliseconds = None;
        self.token_millis = 0;
    }
}

pub fn encode_datagram_frame(
    channel_id: [u8; 16],
    sequence: u64,
    payload: &[u8],
    peer_maximum: usize,
) -> Result<Vec<u8>, DatagramReject> {
    let frame = DatagramFrame::new(channel_id, sequence, payload.to_vec())?;
    let mut encoded = Vec::with_capacity(encoded_len(sequence, payload.len()));
    encoded.extend_from_slice(&[0xa4, 0x00, 0x01, 0x01, 0x50]);
    encoded.extend_from_slice(&channel_id);
    encoded.push(0x02);
    encode_argument(&mut encoded, 0, sequence);
    encoded.push(0x03);
    encode_argument(&mut encoded, 2, payload.len() as u64);
    encoded.extend_from_slice(frame.payload());
    if encoded.len() > peer_maximum {
        return Err(DatagramReject::PeerMaximum);
    }
    Ok(encoded)
}

pub fn decode_datagram_frame(
    wire: &[u8],
    peer_maximum: usize,
) -> Result<DatagramFrame, DatagramReject> {
    if wire.len() > peer_maximum {
        return Err(DatagramReject::PeerMaximum);
    }
    let mut position = 0;
    expect(wire, &mut position, &[0xa4, 0x00, 0x01, 0x01, 0x50])?;
    let channel_end = position
        .checked_add(16)
        .filter(|end| *end <= wire.len())
        .ok_or(DatagramReject::InvalidFrame)?;
    let channel_id: [u8; 16] = wire[position..channel_end]
        .try_into()
        .map_err(|_| DatagramReject::InvalidFrame)?;
    position = channel_end;
    expect(wire, &mut position, &[0x02])?;
    let sequence = decode_argument(wire, &mut position, 0)?;
    expect(wire, &mut position, &[0x03])?;
    let payload_len: usize = decode_argument(wire, &mut position, 2)?
        .try_into()
        .map_err(|_| DatagramReject::InvalidFrame)?;
    if payload_len > MAX_DATAGRAM_PAYLOAD {
        return Err(DatagramReject::PayloadTooLarge);
    }
    let payload_end = position
        .checked_add(payload_len)
        .filter(|end| *end == wire.len())
        .ok_or(DatagramReject::InvalidFrame)?;
    DatagramFrame::new(channel_id, sequence, wire[position..payload_end].to_vec())
}

pub fn max_datagram_payload(
    peer_maximum: usize,
    channel_id: [u8; 16],
    sequence: u64,
) -> Option<usize> {
    if channel_id == [0; 16] || sequence == 0 {
        return None;
    }
    (0..=MAX_DATAGRAM_PAYLOAD)
        .rev()
        .find(|payload_len| encoded_len(sequence, *payload_len) <= peer_maximum)
}

fn encoded_len(sequence: u64, payload_len: usize) -> usize {
    23 + argument_len(sequence) + argument_len(payload_len as u64) + payload_len
}

fn argument_len(value: u64) -> usize {
    match value {
        0..=23 => 1,
        24..=0xff => 2,
        0x100..=0xffff => 3,
        0x1_0000..=0xffff_ffff => 5,
        _ => 9,
    }
}

fn encode_argument(target: &mut Vec<u8>, major: u8, value: u64) {
    let initial = major << 5;
    match value {
        0..=23 => target.push(initial | value as u8),
        24..=0xff => target.extend_from_slice(&[initial | 24, value as u8]),
        0x100..=0xffff => {
            target.push(initial | 25);
            target.extend_from_slice(&(value as u16).to_be_bytes());
        }
        0x1_0000..=0xffff_ffff => {
            target.push(initial | 26);
            target.extend_from_slice(&(value as u32).to_be_bytes());
        }
        _ => {
            target.push(initial | 27);
            target.extend_from_slice(&value.to_be_bytes());
        }
    }
}

fn decode_argument(
    wire: &[u8],
    position: &mut usize,
    expected_major: u8,
) -> Result<u64, DatagramReject> {
    let initial = *wire.get(*position).ok_or(DatagramReject::InvalidFrame)?;
    *position += 1;
    if initial >> 5 != expected_major {
        return Err(DatagramReject::InvalidFrame);
    }
    let additional = initial & 0x1f;
    let (value, encoded_bytes) = match additional {
        value @ 0..=23 => (u64::from(value), 0),
        24 => (read_uint(wire, position, 1)?, 1),
        25 => (read_uint(wire, position, 2)?, 2),
        26 => (read_uint(wire, position, 4)?, 4),
        27 => (read_uint(wire, position, 8)?, 8),
        _ => return Err(DatagramReject::InvalidFrame),
    };
    if (encoded_bytes == 1 && value < 24)
        || (encoded_bytes == 2 && value <= 0xff)
        || (encoded_bytes == 4 && value <= 0xffff)
        || (encoded_bytes == 8 && value <= 0xffff_ffff)
    {
        return Err(DatagramReject::InvalidFrame);
    }
    Ok(value)
}

fn read_uint(wire: &[u8], position: &mut usize, length: usize) -> Result<u64, DatagramReject> {
    let end = position
        .checked_add(length)
        .filter(|end| *end <= wire.len())
        .ok_or(DatagramReject::InvalidFrame)?;
    let mut value = 0_u64;
    for byte in &wire[*position..end] {
        value = (value << 8) | u64::from(*byte);
    }
    *position = end;
    Ok(value)
}

fn expect(wire: &[u8], position: &mut usize, expected: &[u8]) -> Result<(), DatagramReject> {
    let end = position
        .checked_add(expected.len())
        .filter(|end| *end <= wire.len())
        .ok_or(DatagramReject::InvalidFrame)?;
    if &wire[*position..end] != expected {
        return Err(DatagramReject::InvalidFrame);
    }
    *position = end;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const CHANNEL: [u8; 16] = [0x11; 16];

    #[test]
    fn outbound_sequence_rate_fraction_and_audit_are_exact() {
        let mut gate = DatagramGate::new(CHANNEL);
        for expected_sequence in 1..=200 {
            let wire = gate
                .send(b"x", 1_500, 0, |mutation| {
                    assert_eq!(mutation, DatagramAuditMutation::Send);
                    Ok(())
                })
                .unwrap();
            assert_eq!(
                decode_datagram_frame(&wire, 1_500).unwrap().sequence(),
                expected_sequence
            );
        }
        assert_eq!(
            gate.send(b"x", 1_500, 0, |mutation| {
                assert_eq!(
                    mutation,
                    DatagramAuditMutation::Drop(DatagramDropReason::RateLimit)
                );
                Ok(())
            }),
            Err(DatagramReject::RateLimited)
        );
        assert_eq!(
            gate.send(b"x", 1_500, 9, |_| Ok(())),
            Err(DatagramReject::RateLimited)
        );
        let refilled = gate.send(b"x", 1_500, 10, |_| Ok(())).unwrap();
        assert_eq!(
            decode_datagram_frame(&refilled, 1_500).unwrap().sequence(),
            201
        );
        assert_eq!(
            gate.send(b"x", 1_500, 9, |_| Ok(())),
            Err(DatagramReject::BackwardsTime)
        );

        let mut audit_failed = DatagramGate::new([0x22; 16]);
        assert_eq!(
            audit_failed.send(b"x", 1_500, 50, |_| Err(())),
            Err(DatagramReject::AuditUnavailable)
        );
        let first = audit_failed.send(b"x", 1_500, 50, |_| Ok(())).unwrap();
        assert_eq!(decode_datagram_frame(&first, 1_500).unwrap().sequence(), 1);
    }

    #[test]
    fn receive_queue_is_64_replay_safe_and_directionally_independent() {
        let mut gate = DatagramGate::new(CHANNEL);
        for sequence in 1..=64 {
            let frame = DatagramFrame::new(CHANNEL, sequence, vec![sequence as u8]).unwrap();
            assert_eq!(
                gate.receive(frame, 0, |mutation| {
                    assert_eq!(mutation, DatagramAuditMutation::Receive);
                    Ok(())
                }),
                Ok(DatagramReceive::Queued)
            );
        }
        assert_eq!(gate.queued(), 64);
        assert_eq!(
            gate.receive(
                DatagramFrame::new(CHANNEL, 65, vec![65]).unwrap(),
                0,
                |mutation| {
                    assert_eq!(
                        mutation,
                        DatagramAuditMutation::Drop(DatagramDropReason::QueueFull)
                    );
                    Ok(())
                }
            ),
            Ok(DatagramReceive::DroppedQueueFull)
        );
        assert_eq!(gate.queued(), 64);
        assert_eq!(gate.pop(|_| Ok(())), Ok(Some(vec![1])));
        assert_eq!(
            gate.receive(
                DatagramFrame::new(CHANNEL, 65, vec![65]).unwrap(),
                0,
                |_| Ok(())
            ),
            Err(DatagramReject::Replay)
        );

        for _ in 0..200 {
            gate.send(b"out", 1_500, 0, |_| Ok(())).unwrap();
        }
        assert_eq!(
            gate.send(b"out", 1_500, 0, |_| Ok(())),
            Err(DatagramReject::RateLimited)
        );
        assert_eq!(gate.queued(), 63);
    }

    #[test]
    fn audit_failure_and_deactivation_preserve_queue_and_replay_tombstone() {
        let mut gate = DatagramGate::new(CHANNEL);
        let frame = DatagramFrame::new(CHANNEL, 1, b"queued-secret".to_vec()).unwrap();
        assert_eq!(
            gate.receive(frame.clone(), 100, |_| Err(())),
            Err(DatagramReject::AuditUnavailable)
        );
        assert_eq!(gate.queued(), 0);
        assert_eq!(
            gate.receive(frame, 100, |_| Ok(())),
            Ok(DatagramReceive::Queued)
        );
        assert_eq!(gate.pop(|_| Err(())), Err(DatagramReject::AuditUnavailable));
        assert_eq!(gate.queued(), 1);

        gate.deactivate();
        assert_eq!(gate.queued(), 0);
        assert_eq!(
            gate.receive(
                DatagramFrame::new(CHANNEL, 1, vec![]).unwrap(),
                100,
                |_| Ok(())
            ),
            Err(DatagramReject::Replay)
        );
        assert_eq!(
            gate.receive(
                DatagramFrame::new(CHANNEL, 2, vec![]).unwrap(),
                100,
                |_| Ok(())
            ),
            Err(DatagramReject::InvalidState)
        );
        assert_eq!(
            gate.send(b"x", 1_500, 100, |_| Ok(())),
            Err(DatagramReject::InvalidState)
        );
        assert_eq!(gate.pop(|_| Ok(())), Err(DatagramReject::InvalidState));
    }

    #[test]
    fn outbound_u64_max_is_emitted_once_and_never_wraps() {
        let channel_id = [0x44; 16];
        let mut gate = DatagramGate::new(channel_id);
        gate.next_outbound = Some(u64::MAX);

        let wire = gate.send(b"last", 1_500, 0, |_| Ok(())).unwrap();
        assert_eq!(
            decode_datagram_frame(&wire, 1_500).unwrap().sequence(),
            u64::MAX
        );
        assert_eq!(
            gate.send(b"never", 1_500, 0, |_| Ok(())),
            Err(DatagramReject::SequenceExhausted)
        );
    }

    #[test]
    fn elapsed_u64_max_refills_by_clamping_without_arithmetic_overflow() {
        let mut gate = DatagramGate::new([0x45; 16]);
        for _ in 0..200 {
            gate.send(b"x", 1_500, 0, |_| Ok(())).unwrap();
        }
        assert!(gate.send(b"x", 1_500, u64::MAX, |_| Ok(())).is_ok());
    }
}
