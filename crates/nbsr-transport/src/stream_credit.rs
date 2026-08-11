//! Closed, bounded codec and admission window for the `nbsr-stream-credit-1` profile.
//!
//! The codec recognizes only the pinned integer-keyed CBOR map. The admission
//! state keeps one current and at most one draining fixed-size credit epoch.

use std::collections::HashMap;

pub const STREAM_CREDIT_PROFILE_ID: &str = "nbsr-stream-credit-1";
pub const STREAM_CREDIT_COUNT: u8 = 64;
pub const STREAM_CREDIT_LOW_WATERMARK: u8 = 16;
pub const MAX_STREAM_CREDIT_PREFACE_BYTES: usize = 128;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StreamCreditProfile {
    Legacy,
    V1,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StreamCreditReject {
    MalformedPreface,
    ProfileUnsupported,
    Downgrade,
    FallbackForbidden,
    InvalidSlot,
    WrongChannel,
    WrongGeneration,
    WrongSession,
    WrongStream,
    DuplicateStream,
    DuplicateSlot,
    StaleEpoch,
    Exhausted,
    RefillNotDue,
    RefillPending,
    DrainingEpoch,
    EpochExhausted,
    GrantMismatch,
    Revoked,
    Expired,
    OverCapacity,
    ReplayCapacity,
    AuditUnavailable,
    InvalidState,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StreamCreditPreface {
    pub channel_id: [u8; 16],
    pub channel_generation: u64,
    pub credit_epoch: u64,
    pub credit_slot: u8,
    pub quic_stream_id: u64,
}

/// Identity already authenticated by the active transport session.  The
/// preface deliberately does not repeat a session identifier or RouteGrant.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StreamCreditContext {
    /// Session identity bound when the channel was activated.
    pub session_id: [u8; 16],
    /// Identity of the authenticated QUIC session delivering this stream.
    pub authenticated_session_id: [u8; 16],
    pub channel_id: [u8; 16],
    pub channel_generation: u64,
    pub quic_stream_id: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct StreamCreditBinding {
    pub(crate) profile: StreamCreditProfile,
    pub(crate) session_id: [u8; 16],
    pub(crate) route_id: [u8; 16],
    pub(crate) route_grant_digest: [u8; 32],
    pub(crate) channel_id: [u8; 16],
    pub(crate) channel_generation: u64,
    pub(crate) revocation_generation: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[allow(dead_code)] // Sender/refill transport wiring is a later task; Task 2 pins the state API.
pub(crate) struct StreamCreditAllocation {
    pub(crate) credit_epoch: u64,
    pub(crate) credit_slot: u8,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct PreparedCreditConsume {
    binding: StreamCreditBinding,
    credit_epoch: u64,
    credit_slot: u8,
}

#[derive(Clone, Copy)]
struct CreditEpoch {
    number: u64,
    used: u64,
}

#[derive(Clone, Copy)]
struct CreditWindowState {
    current: CreditEpoch,
    draining: Option<CreditEpoch>,
    #[allow(dead_code)] // Used by the pinned refill API before runtime control wiring.
    pending_refill: Option<u64>,
}

struct CreditWindowEntry {
    profile: StreamCreditProfile,
    route_id: [u8; 16],
    route_grant_digest: [u8; 32],
    channel_generation: u64,
    revocation_generation: u64,
    state: CreditWindowState,
}

pub(crate) struct StreamCreditWindows {
    session_id: Option<[u8; 16]>,
    channels: HashMap<[u8; 16], CreditWindowEntry>,
}

impl StreamCreditWindows {
    pub(crate) fn new() -> Self {
        Self {
            session_id: None,
            channels: HashMap::new(),
        }
    }

    pub(crate) fn activate(
        &mut self,
        binding: StreamCreditBinding,
    ) -> Result<(), StreamCreditReject> {
        self.activate_epoch(binding, 1)
    }

    #[cfg(test)]
    fn activate_at(
        &mut self,
        binding: StreamCreditBinding,
        epoch: u64,
    ) -> Result<(), StreamCreditReject> {
        self.activate_epoch(binding, epoch)
    }

    fn activate_epoch(
        &mut self,
        binding: StreamCreditBinding,
        epoch: u64,
    ) -> Result<(), StreamCreditReject> {
        if binding.profile != StreamCreditProfile::V1 {
            return Err(StreamCreditReject::ProfileUnsupported);
        }
        if binding.channel_generation == 0 || binding.revocation_generation == 0 || epoch == 0 {
            return Err(StreamCreditReject::InvalidState);
        }
        match self.session_id {
            Some(session_id) if session_id != binding.session_id => {
                return Err(StreamCreditReject::WrongSession);
            }
            None => self.session_id = Some(binding.session_id),
            Some(_) => {}
        }
        if self.channels.contains_key(&binding.channel_id) {
            return Err(StreamCreditReject::InvalidState);
        }
        self.channels.insert(
            binding.channel_id,
            CreditWindowEntry {
                profile: binding.profile,
                route_id: binding.route_id,
                route_grant_digest: binding.route_grant_digest,
                channel_generation: binding.channel_generation,
                revocation_generation: binding.revocation_generation,
                state: CreditWindowState {
                    current: CreditEpoch {
                        number: epoch,
                        used: 0,
                    },
                    draining: None,
                    pending_refill: None,
                },
            },
        );
        Ok(())
    }

    #[allow(dead_code)] // Sender-side allocation is wired by the runtime task.
    pub(crate) fn allocate(
        &mut self,
        binding: &StreamCreditBinding,
    ) -> Result<StreamCreditAllocation, StreamCreditReject> {
        let entry = self.entry_mut(binding)?;
        let available = !entry.state.current.used;
        if available == 0 {
            return Err(StreamCreditReject::Exhausted);
        }
        let slot = available.trailing_zeros() as u8;
        entry.state.current.used |= 1_u64 << slot;
        Ok(StreamCreditAllocation {
            credit_epoch: entry.state.current.number,
            credit_slot: slot,
        })
    }

    #[allow(dead_code)] // Refill control transport is wired by the runtime task.
    pub(crate) fn request_refill(
        &mut self,
        binding: &StreamCreditBinding,
    ) -> Result<u64, StreamCreditReject> {
        let entry = self.entry_mut(binding)?;
        if entry.state.pending_refill.is_some() {
            return Err(StreamCreditReject::RefillPending);
        }
        let remaining = STREAM_CREDIT_COUNT - entry.state.current.used.count_ones() as u8;
        if remaining > STREAM_CREDIT_LOW_WATERMARK {
            return Err(StreamCreditReject::RefillNotDue);
        }
        let next = entry
            .state
            .current
            .number
            .checked_add(1)
            .ok_or(StreamCreditReject::EpochExhausted)?;
        entry.state.pending_refill = Some(next);
        Ok(next)
    }

    #[allow(dead_code)] // Refill control transport is wired by the runtime task.
    pub(crate) fn activate_refill(
        &mut self,
        binding: &StreamCreditBinding,
        epoch: u64,
    ) -> Result<(), StreamCreditReject> {
        let entry = self.entry_mut(binding)?;
        if entry.state.draining.is_some() {
            return Err(StreamCreditReject::DrainingEpoch);
        }
        let expected = entry
            .state
            .current
            .number
            .checked_add(1)
            .ok_or(StreamCreditReject::EpochExhausted)?;
        if entry.state.pending_refill != Some(epoch) || epoch != expected {
            return Err(StreamCreditReject::InvalidState);
        }
        entry.state.draining = Some(entry.state.current);
        entry.state.current = CreditEpoch {
            number: epoch,
            used: 0,
        };
        entry.state.pending_refill = None;
        Ok(())
    }

    #[allow(dead_code)] // Refill control transport is wired by the runtime task.
    pub(crate) fn cancel_refill(
        &mut self,
        binding: &StreamCreditBinding,
    ) -> Result<(), StreamCreditReject> {
        let entry = self.entry_mut(binding)?;
        entry
            .state
            .pending_refill
            .take()
            .map(|_| ())
            .ok_or(StreamCreditReject::InvalidState)
    }

    pub(crate) fn prepare_consume(
        &self,
        binding: &StreamCreditBinding,
        credit_epoch: u64,
        credit_slot: u8,
    ) -> Result<PreparedCreditConsume, StreamCreditReject> {
        if credit_slot >= STREAM_CREDIT_COUNT {
            return Err(StreamCreditReject::InvalidSlot);
        }
        let entry = self.entry(binding)?;
        let epoch = Self::epoch(&entry.state, credit_epoch)?;
        if epoch.used & (1_u64 << credit_slot) != 0 {
            return Err(StreamCreditReject::DuplicateSlot);
        }
        Ok(PreparedCreditConsume {
            binding: *binding,
            credit_epoch,
            credit_slot,
        })
    }

    pub(crate) fn commit_consume(
        &mut self,
        prepared: PreparedCreditConsume,
    ) -> Result<(), StreamCreditReject> {
        let entry = self.entry_mut(&prepared.binding)?;
        let epoch = Self::epoch_mut(&mut entry.state, prepared.credit_epoch)?;
        let bit = 1_u64 << prepared.credit_slot;
        if epoch.used & bit != 0 {
            return Err(StreamCreditReject::DuplicateSlot);
        }
        epoch.used |= bit;
        Ok(())
    }

    #[allow(dead_code)] // Epoch retirement control is wired by the runtime task.
    pub(crate) fn retire(
        &mut self,
        binding: &StreamCreditBinding,
        epoch: u64,
    ) -> Result<(), StreamCreditReject> {
        let entry = self.entry_mut(binding)?;
        if entry
            .state
            .draining
            .is_some_and(|value| value.number == epoch)
        {
            entry.state.draining = None;
            Ok(())
        } else {
            Err(StreamCreditReject::StaleEpoch)
        }
    }

    pub(crate) fn remove_channel(&mut self, session_id: [u8; 16], channel_id: [u8; 16]) {
        if self.session_id == Some(session_id) {
            self.channels.remove(&channel_id);
        }
    }

    pub(crate) fn remove_session(&mut self, session_id: [u8; 16]) {
        if self.session_id == Some(session_id) {
            self.channels.clear();
            self.session_id = None;
        }
    }

    pub(crate) fn has_channel(&self, session_id: [u8; 16], channel_id: [u8; 16]) -> bool {
        self.session_id == Some(session_id) && self.channels.contains_key(&channel_id)
    }

    fn entry(
        &self,
        binding: &StreamCreditBinding,
    ) -> Result<&CreditWindowEntry, StreamCreditReject> {
        if self.session_id != Some(binding.session_id) {
            return Err(StreamCreditReject::WrongSession);
        }
        let entry = self
            .channels
            .get(&binding.channel_id)
            .ok_or(StreamCreditReject::WrongChannel)?;
        Self::validate_entry(entry, binding)?;
        Ok(entry)
    }

    fn entry_mut(
        &mut self,
        binding: &StreamCreditBinding,
    ) -> Result<&mut CreditWindowEntry, StreamCreditReject> {
        if self.session_id != Some(binding.session_id) {
            return Err(StreamCreditReject::WrongSession);
        }
        let entry = self
            .channels
            .get_mut(&binding.channel_id)
            .ok_or(StreamCreditReject::WrongChannel)?;
        Self::validate_entry(entry, binding)?;
        Ok(entry)
    }

    fn validate_entry(
        entry: &CreditWindowEntry,
        binding: &StreamCreditBinding,
    ) -> Result<(), StreamCreditReject> {
        if entry.profile != binding.profile {
            return Err(StreamCreditReject::ProfileUnsupported);
        }
        if entry.route_id != binding.route_id
            || entry.route_grant_digest != binding.route_grant_digest
        {
            return Err(StreamCreditReject::GrantMismatch);
        }
        if entry.channel_generation != binding.channel_generation {
            return Err(StreamCreditReject::WrongGeneration);
        }
        if entry.revocation_generation != binding.revocation_generation {
            return Err(StreamCreditReject::Revoked);
        }
        Ok(())
    }

    fn epoch(state: &CreditWindowState, number: u64) -> Result<&CreditEpoch, StreamCreditReject> {
        if state.current.number == number {
            Ok(&state.current)
        } else if let Some(draining) = state
            .draining
            .as_ref()
            .filter(|value| value.number == number)
        {
            Ok(draining)
        } else {
            Err(StreamCreditReject::StaleEpoch)
        }
    }

    fn epoch_mut(
        state: &mut CreditWindowState,
        number: u64,
    ) -> Result<&mut CreditEpoch, StreamCreditReject> {
        if state.current.number == number {
            Ok(&mut state.current)
        } else if let Some(draining) = state
            .draining
            .as_mut()
            .filter(|value| value.number == number)
        {
            Ok(draining)
        } else {
            Err(StreamCreditReject::StaleEpoch)
        }
    }

    #[cfg(test)]
    pub(crate) fn used_bitmap(&self, binding: &StreamCreditBinding, epoch: u64) -> Option<u64> {
        self.entry(binding)
            .ok()
            .and_then(|entry| Self::epoch(&entry.state, epoch).ok())
            .map(|value| value.used)
    }

    #[cfg(test)]
    fn pending_refill(&self, binding: &StreamCreditBinding) -> Option<u64> {
        self.entry(binding)
            .ok()
            .and_then(|entry| entry.state.pending_refill)
    }

    #[cfg(test)]
    fn recognized_epochs(&self, binding: &StreamCreditBinding) -> Option<(u64, Option<u64>)> {
        self.entry(binding).ok().map(|entry| {
            (
                entry.state.current.number,
                entry.state.draining.map(|value| value.number),
            )
        })
    }

    #[cfg(test)]
    fn len(&self) -> usize {
        self.channels.len()
    }
}

impl StreamCreditProfile {
    /// Selects the profile before activation.  An explicit legacy selection
    /// is allowed only when local policy does not require stream credits.
    pub fn select(
        credits_required: bool,
        peer_profile: Option<&str>,
        explicit_legacy: bool,
    ) -> Result<Self, StreamCreditReject> {
        if explicit_legacy {
            return if credits_required {
                Err(StreamCreditReject::FallbackForbidden)
            } else {
                Ok(Self::Legacy)
            };
        }
        match peer_profile {
            Some(STREAM_CREDIT_PROFILE_ID) => Ok(Self::V1),
            Some(_) => Err(StreamCreditReject::ProfileUnsupported),
            None if credits_required => Err(StreamCreditReject::Downgrade),
            None => Ok(Self::Legacy),
        }
    }
}

pub fn encode_stream_credit_preface(
    preface: &StreamCreditPreface,
) -> Result<Vec<u8>, StreamCreditReject> {
    if preface.channel_generation == 0
        || preface.credit_epoch == 0
        || preface.credit_slot >= STREAM_CREDIT_COUNT
        || !source_bidirectional_stream(preface.quic_stream_id)
    {
        return Err(StreamCreditReject::MalformedPreface);
    }

    let mut body = Vec::with_capacity(32);
    body.push(0xa6);
    cbor_uint(&mut body, 0);
    cbor_uint(&mut body, 1);
    cbor_uint(&mut body, 1);
    cbor_bytes(&mut body, &preface.channel_id);
    cbor_uint(&mut body, 2);
    cbor_uint(&mut body, preface.channel_generation);
    cbor_uint(&mut body, 3);
    cbor_uint(&mut body, preface.credit_epoch);
    cbor_uint(&mut body, 4);
    cbor_uint(&mut body, u64::from(preface.credit_slot));
    cbor_uint(&mut body, 5);
    cbor_uint(&mut body, preface.quic_stream_id);
    if body.len() > MAX_STREAM_CREDIT_PREFACE_BYTES {
        return Err(StreamCreditReject::MalformedPreface);
    }

    let mut encoded = Vec::with_capacity(body.len() + 2);
    encode_quic_varint(&mut encoded, body.len() as u64);
    encoded.extend_from_slice(&body);
    Ok(encoded)
}

pub fn decode_stream_credit_preface(
    wire: &[u8],
    context: StreamCreditContext,
) -> Result<StreamCreditPreface, StreamCreditReject> {
    if context.session_id != context.authenticated_session_id {
        return Err(StreamCreditReject::WrongSession);
    }
    let (body_length, prefix_length) = decode_quic_varint(wire)?;
    let body_length: usize = body_length
        .try_into()
        .map_err(|_| StreamCreditReject::MalformedPreface)?;
    if body_length > MAX_STREAM_CREDIT_PREFACE_BYTES
        || wire.len() != prefix_length.saturating_add(body_length)
    {
        return Err(StreamCreditReject::MalformedPreface);
    }
    let body = wire
        .get(prefix_length..)
        .ok_or(StreamCreditReject::MalformedPreface)?;
    let mut decoder = CborDecoder::new(body);
    decoder.exact_map(6)?;
    decoder.exact_uint(0, 1)?;
    decoder.exact_key(1)?;
    let channel_id = decoder.bytes_16()?;
    decoder.exact_key(2)?;
    let channel_generation = decoder.uint()?;
    decoder.exact_key(3)?;
    let credit_epoch = decoder.uint()?;
    decoder.exact_key(4)?;
    let credit_slot = decoder.uint()?;
    decoder.exact_key(5)?;
    let quic_stream_id = decoder.uint()?;
    if !decoder.finished() || channel_generation == 0 || credit_epoch == 0 {
        return Err(StreamCreditReject::MalformedPreface);
    }
    if credit_slot >= u64::from(STREAM_CREDIT_COUNT) {
        return Err(StreamCreditReject::InvalidSlot);
    }
    if !source_bidirectional_stream(quic_stream_id) {
        return Err(StreamCreditReject::MalformedPreface);
    }
    if channel_id != context.channel_id {
        return Err(StreamCreditReject::WrongChannel);
    }
    if channel_generation != context.channel_generation {
        return Err(StreamCreditReject::WrongGeneration);
    }
    if quic_stream_id != context.quic_stream_id {
        return Err(StreamCreditReject::WrongStream);
    }
    Ok(StreamCreditPreface {
        channel_id,
        channel_generation,
        credit_epoch,
        credit_slot: credit_slot as u8,
        quic_stream_id,
    })
}

fn source_bidirectional_stream(stream_id: u64) -> bool {
    stream_id != 0 && stream_id.is_multiple_of(4)
}

fn encode_quic_varint(output: &mut Vec<u8>, value: u64) {
    match value {
        0..=63 => output.push(value as u8),
        64..=16_383 => output.extend_from_slice(&((value as u16 | 0x4000).to_be_bytes())),
        16_384..=1_073_741_823 => {
            output.extend_from_slice(&((value as u32 | 0x8000_0000).to_be_bytes()))
        }
        _ => output.extend_from_slice(&(value | 0xc000_0000_0000_0000).to_be_bytes()),
    }
}

fn decode_quic_varint(wire: &[u8]) -> Result<(u64, usize), StreamCreditReject> {
    let first = *wire.first().ok_or(StreamCreditReject::MalformedPreface)?;
    let length = 1_usize << (first >> 6);
    let bytes = wire
        .get(..length)
        .ok_or(StreamCreditReject::MalformedPreface)?;
    let value = match length {
        1 => u64::from(bytes[0] & 0x3f),
        2 => u64::from(u16::from_be_bytes([bytes[0], bytes[1]]) & 0x3fff),
        4 => u64::from(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]) & 0x3fff_ffff),
        8 => u64::from_be_bytes([
            bytes[0] & 0x3f,
            bytes[1],
            bytes[2],
            bytes[3],
            bytes[4],
            bytes[5],
            bytes[6],
            bytes[7],
        ]),
        _ => unreachable!("QUIC variable length is two bits"),
    };
    let shortest = match value {
        0..=63 => 1,
        64..=16_383 => 2,
        16_384..=1_073_741_823 => 4,
        _ => 8,
    };
    (length == shortest)
        .then_some((value, length))
        .ok_or(StreamCreditReject::MalformedPreface)
}

fn cbor_uint(output: &mut Vec<u8>, value: u64) {
    cbor_argument(output, 0, value);
}

fn cbor_bytes(output: &mut Vec<u8>, bytes: &[u8]) {
    cbor_argument(output, 2, bytes.len() as u64);
    output.extend_from_slice(bytes);
}

fn cbor_argument(output: &mut Vec<u8>, major: u8, value: u64) {
    match value {
        0..=23 => output.push((major << 5) | value as u8),
        24..=255 => output.extend_from_slice(&[(major << 5) | 24, value as u8]),
        256..=65_535 => {
            output.push((major << 5) | 25);
            output.extend_from_slice(&(value as u16).to_be_bytes());
        }
        65_536..=4_294_967_295 => {
            output.push((major << 5) | 26);
            output.extend_from_slice(&(value as u32).to_be_bytes());
        }
        _ => {
            output.push((major << 5) | 27);
            output.extend_from_slice(&value.to_be_bytes());
        }
    }
}

struct CborDecoder<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> CborDecoder<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, position: 0 }
    }

    fn exact_map(&mut self, length: u64) -> Result<(), StreamCreditReject> {
        (self.argument(5)? == length)
            .then_some(())
            .ok_or(StreamCreditReject::MalformedPreface)
    }

    fn exact_key(&mut self, key: u64) -> Result<(), StreamCreditReject> {
        (self.uint()? == key)
            .then_some(())
            .ok_or(StreamCreditReject::MalformedPreface)
    }

    fn exact_uint(&mut self, key: u64, value: u64) -> Result<(), StreamCreditReject> {
        self.exact_key(key)?;
        (self.uint()? == value)
            .then_some(())
            .ok_or(StreamCreditReject::ProfileUnsupported)
    }

    fn uint(&mut self) -> Result<u64, StreamCreditReject> {
        self.argument(0)
    }

    fn bytes_16(&mut self) -> Result<[u8; 16], StreamCreditReject> {
        let length: usize = self
            .argument(2)?
            .try_into()
            .map_err(|_| StreamCreditReject::MalformedPreface)?;
        if length != 16 {
            return Err(StreamCreditReject::MalformedPreface);
        }
        let slice = self.take_slice(length)?;
        slice
            .try_into()
            .map_err(|_| StreamCreditReject::MalformedPreface)
    }

    fn argument(&mut self, expected_major: u8) -> Result<u64, StreamCreditReject> {
        let initial = self.take()?;
        if initial >> 5 != expected_major {
            return Err(StreamCreditReject::MalformedPreface);
        }
        match initial & 0x1f {
            value @ 0..=23 => Ok(u64::from(value)),
            24 => {
                let value = u64::from(self.take()?);
                self.preferred(value, 24)
            }
            25 => {
                let bytes = self.take_slice(2)?;
                self.preferred(u64::from(u16::from_be_bytes([bytes[0], bytes[1]])), 256)
            }
            26 => {
                let bytes = self.take_slice(4)?;
                self.preferred(
                    u64::from(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]])),
                    65_536,
                )
            }
            27 => {
                let bytes = self.take_slice(8)?;
                self.preferred(
                    u64::from_be_bytes([
                        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6],
                        bytes[7],
                    ]),
                    4_294_967_296,
                )
            }
            _ => Err(StreamCreditReject::MalformedPreface),
        }
    }

    fn preferred(&self, value: u64, minimum: u64) -> Result<u64, StreamCreditReject> {
        (value >= minimum)
            .then_some(value)
            .ok_or(StreamCreditReject::MalformedPreface)
    }

    fn take(&mut self) -> Result<u8, StreamCreditReject> {
        let value = *self
            .bytes
            .get(self.position)
            .ok_or(StreamCreditReject::MalformedPreface)?;
        self.position += 1;
        Ok(value)
    }

    fn take_slice(&mut self, length: usize) -> Result<&'a [u8], StreamCreditReject> {
        let end = self
            .position
            .checked_add(length)
            .ok_or(StreamCreditReject::MalformedPreface)?;
        let value = self
            .bytes
            .get(self.position..end)
            .ok_or(StreamCreditReject::MalformedPreface)?;
        self.position = end;
        Ok(value)
    }

    fn finished(&self) -> bool {
        self.position == self.bytes.len()
    }
}

#[cfg(test)]
mod lifecycle_tests {
    use std::mem::size_of;

    use super::*;

    fn binding(id: u8) -> StreamCreditBinding {
        StreamCreditBinding {
            profile: StreamCreditProfile::V1,
            session_id: [0x10; 16],
            route_id: [id.wrapping_add(0x40); 16],
            route_grant_digest: [id.wrapping_add(0x80); 32],
            channel_id: [id; 16],
            channel_generation: 1,
            revocation_generation: 1,
        }
    }

    #[test]
    fn exact_sixty_four_slots_exhaust_without_wrapping_or_allocation() {
        let authority = binding(1);
        let mut windows = StreamCreditWindows::new();
        windows.activate(authority).expect("fresh channel");
        for expected_slot in 0..STREAM_CREDIT_COUNT {
            assert_eq!(
                windows.allocate(&authority).expect("credit available"),
                StreamCreditAllocation {
                    credit_epoch: 1,
                    credit_slot: expected_slot,
                }
            );
        }
        assert_eq!(
            windows.allocate(&authority),
            Err(StreamCreditReject::Exhausted)
        );
        assert_eq!(windows.used_bitmap(&authority, 1), Some(u64::MAX));
    }

    #[test]
    fn consume_rejects_invalid_duplicate_and_wrong_authority_without_mutation() {
        let authority = binding(1);
        let mut windows = StreamCreditWindows::new();
        windows.activate(authority).unwrap();

        assert_eq!(
            windows.prepare_consume(&authority, 1, 64),
            Err(StreamCreditReject::InvalidSlot)
        );
        for (wrong, expected) in [
            (
                StreamCreditBinding {
                    profile: StreamCreditProfile::Legacy,
                    ..authority
                },
                StreamCreditReject::ProfileUnsupported,
            ),
            (
                StreamCreditBinding {
                    session_id: [9; 16],
                    ..authority
                },
                StreamCreditReject::WrongSession,
            ),
            (
                StreamCreditBinding {
                    route_id: [9; 16],
                    ..authority
                },
                StreamCreditReject::GrantMismatch,
            ),
            (
                StreamCreditBinding {
                    route_grant_digest: [9; 32],
                    ..authority
                },
                StreamCreditReject::GrantMismatch,
            ),
            (
                StreamCreditBinding {
                    channel_id: [9; 16],
                    ..authority
                },
                StreamCreditReject::WrongChannel,
            ),
            (
                StreamCreditBinding {
                    channel_generation: 2,
                    ..authority
                },
                StreamCreditReject::WrongGeneration,
            ),
            (
                StreamCreditBinding {
                    revocation_generation: 2,
                    ..authority
                },
                StreamCreditReject::Revoked,
            ),
        ] {
            assert_eq!(windows.prepare_consume(&wrong, 1, 0), Err(expected));
        }
        let prepared = windows.prepare_consume(&authority, 1, 0).unwrap();
        windows.commit_consume(prepared).unwrap();
        assert_eq!(
            windows.prepare_consume(&authority, 1, 0),
            Err(StreamCreditReject::DuplicateSlot)
        );
        assert_eq!(windows.used_bitmap(&authority, 1), Some(1));
    }

    #[test]
    fn refill_is_single_bounded_and_keeps_current_usable_until_activation() {
        let authority = binding(1);
        let mut windows = StreamCreditWindows::new();
        windows.activate(authority).unwrap();
        for _ in 0..47 {
            windows.allocate(&authority).unwrap();
        }
        assert_eq!(
            windows.request_refill(&authority),
            Err(StreamCreditReject::RefillNotDue)
        );
        windows.allocate(&authority).unwrap();
        assert_eq!(windows.request_refill(&authority), Ok(2));
        assert_eq!(
            windows.request_refill(&authority),
            Err(StreamCreditReject::RefillPending)
        );
        assert_eq!(windows.allocate(&authority).unwrap().credit_epoch, 1);
        windows.cancel_refill(&authority).unwrap();
        assert_eq!(windows.pending_refill(&authority), None);
        assert_eq!(windows.request_refill(&authority), Ok(2));
        assert_eq!(windows.allocate(&authority).unwrap().credit_epoch, 1);
        windows.activate_refill(&authority, 2).unwrap();
        assert_eq!(windows.recognized_epochs(&authority), Some((2, Some(1))));
        assert_eq!(
            windows.allocate(&authority).unwrap(),
            StreamCreditAllocation {
                credit_epoch: 2,
                credit_slot: 0
            }
        );
    }

    #[test]
    fn draining_and_current_accept_old_new_reordering_but_never_a_third_epoch() {
        let authority = binding(1);
        let mut windows = StreamCreditWindows::new();
        windows.activate(authority).unwrap();
        for _ in 0..48 {
            windows.allocate(&authority).unwrap();
        }
        windows.request_refill(&authority).unwrap();
        windows.activate_refill(&authority, 2).unwrap();
        let new = windows.prepare_consume(&authority, 2, 63).unwrap();
        windows.commit_consume(new).unwrap();
        let old = windows.prepare_consume(&authority, 1, 63).unwrap();
        windows.commit_consume(old).unwrap();
        assert_eq!(
            windows.request_refill(&authority),
            Err(StreamCreditReject::RefillNotDue)
        );
        for _ in 0..48 {
            windows.allocate(&authority).unwrap();
        }
        assert_eq!(windows.request_refill(&authority), Ok(3));
        assert_eq!(
            windows.activate_refill(&authority, 3),
            Err(StreamCreditReject::DrainingEpoch)
        );
        windows.retire(&authority, 1).unwrap();
        windows.activate_refill(&authority, 3).unwrap();
        assert_eq!(
            windows.prepare_consume(&authority, 1, 1),
            Err(StreamCreditReject::StaleEpoch)
        );
        assert_eq!(windows.recognized_epochs(&authority), Some((3, Some(2))));
    }

    #[test]
    fn same_slot_race_commits_once_and_epoch_never_wraps() {
        let authority = binding(1);
        let mut windows = StreamCreditWindows::new();
        windows.activate_at(authority, u64::MAX).unwrap();
        let first = windows.prepare_consume(&authority, u64::MAX, 7).unwrap();
        let second = windows.prepare_consume(&authority, u64::MAX, 7).unwrap();
        windows.commit_consume(first).unwrap();
        assert_eq!(
            windows.commit_consume(second),
            Err(StreamCreditReject::DuplicateSlot)
        );
        for _ in 0..48 {
            windows.allocate(&authority).unwrap();
        }
        assert_eq!(
            windows.request_refill(&authority),
            Err(StreamCreditReject::EpochExhausted)
        );
    }

    #[test]
    fn dropped_prepare_models_validation_or_audit_failure_without_consuming_credit() {
        let authority = binding(1);
        let mut windows = StreamCreditWindows::new();
        windows.activate(authority).unwrap();
        {
            let _rejected_before_commit = windows.prepare_consume(&authority, 1, 9).unwrap();
        }
        assert_eq!(windows.used_bitmap(&authority, 1), Some(0));
        let retry = windows.prepare_consume(&authority, 1, 9).unwrap();
        windows.commit_consume(retry).unwrap();
        assert_eq!(windows.used_bitmap(&authority, 1), Some(1 << 9));
    }

    #[test]
    fn channel_cleanup_and_thousands_of_never_consumed_windows_remain_fixed_size() {
        assert!(size_of::<CreditWindowState>() <= 64);
        let mut windows = StreamCreditWindows::new();
        for id in 1..=4_000_u16 {
            let mut authority = binding((id & 0xff) as u8);
            authority.channel_id = id.to_be_bytes().repeat(8).try_into().unwrap();
            windows.activate(authority).unwrap();
            for invalid in [64, 127, 255] {
                assert_eq!(
                    windows.prepare_consume(&authority, 1, invalid),
                    Err(StreamCreditReject::InvalidSlot)
                );
            }
            assert_eq!(
                windows.prepare_consume(&authority, 0, 0),
                Err(StreamCreditReject::StaleEpoch)
            );
        }
        assert_eq!(windows.len(), 4_000);
        let flood = binding(254);
        windows.activate(flood).unwrap();
        for slot in 0..48 {
            let prepared = windows.prepare_consume(&flood, 1, slot).unwrap();
            windows.commit_consume(prepared).unwrap();
        }
        assert_eq!(windows.request_refill(&flood), Ok(2));
        for _ in 0..10_000 {
            assert_eq!(
                windows.request_refill(&flood),
                Err(StreamCreditReject::RefillPending)
            );
            assert_eq!(
                windows.prepare_consume(&flood, 1, 0),
                Err(StreamCreditReject::DuplicateSlot)
            );
            assert_eq!(
                windows.prepare_consume(&flood, 1, 64),
                Err(StreamCreditReject::InvalidSlot)
            );
        }
        let target = binding(255);
        windows.activate(target).unwrap();
        windows.remove_channel(target.session_id, target.channel_id);
        assert_eq!(
            windows.prepare_consume(&target, 1, 0),
            Err(StreamCreditReject::WrongChannel)
        );
    }
}
