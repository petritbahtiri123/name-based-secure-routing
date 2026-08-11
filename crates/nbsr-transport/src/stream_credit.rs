//! Closed, bounded codec for the `nbsr-stream-credit-1` stream preface.
//!
//! This module intentionally contains no admission state.  It only selects
//! the explicitly negotiated profile and validates one preface against the
//! authenticated channel/session/QUIC identities supplied by the caller.

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
