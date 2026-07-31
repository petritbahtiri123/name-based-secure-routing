//! Bounded, deterministic Core v0.2 control-envelope validation.
//!
//! This module intentionally performs the deterministic CBOR structural gate
//! before interpreting a control message.  It does not allocate any route or
//! stream state and it does not expose origin metadata.

use ed25519_dalek::{Signature, VerifyingKey};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CoreV02Limits {
    pub max_frame_bytes: usize,
    pub max_depth: usize,
    pub max_map_pairs: usize,
    pub max_array_items: usize,
}

impl Default for CoreV02Limits {
    fn default() -> Self {
        Self {
            max_frame_bytes: 65_536,
            max_depth: 16,
            max_map_pairs: 128,
            max_array_items: 128,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CoreV02Reject {
    ProfileUnsupported,
    OverCapacity,
    Downgrade,
    GrantInvalid,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CoreV02MessageType {
    ClientHello,
    EdgeHello,
    RouteOpen,
    RouteAccept,
    RouteReject,
    StreamOpen,
    StreamAccept,
    StreamReject,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CoreV02Envelope {
    message_type: CoreV02MessageType,
    wire: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RouteGrantIssuer {
    pub kid: Vec<u8>,
    pub public_key: [u8; 32],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValidatedRouteGrant {
    pub issuer_kid: Vec<u8>,
    pub payload: Vec<u8>,
}

/// Validates the frozen COSE Sign1 wrapper in the caller-provided issuer trust
/// context.  It deliberately does not choose a trust anchor itself.
pub fn validate_route_grant_sign1(
    wire: &[u8],
    trusted_issuers: &[RouteGrantIssuer],
) -> Result<ValidatedRouteGrant, CoreV02Reject> {
    if wire.first() != Some(&0xd2) {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let limits = CoreV02Limits {
        max_frame_bytes: 32_768,
        ..CoreV02Limits::default()
    };
    let mut decoder = Decoder::new(&wire[1..], limits);
    let sign1 = decoder.node(0)?;
    if decoder.position != wire.len() - 1 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let fields = array(&sign1)?;
    if fields.len() != 4 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let protected = bytes(&fields[0])?;
    let unprotected = map(&fields[1])?;
    if !unprotected.is_empty() {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let payload = bytes(&fields[2])?;
    if payload.is_empty() || payload.len() > 32_768 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let signature = bytes(&fields[3])?;
    if signature.len() != 64 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let protected = decode_protected_header(protected)?;
    let issuer = trusted_issuers
        .iter()
        .find(|issuer| issuer.kid == protected.kid)
        .ok_or(CoreV02Reject::GrantInvalid)?;
    let key =
        VerifyingKey::from_bytes(&issuer.public_key).map_err(|_| CoreV02Reject::GrantInvalid)?;
    let signature = Signature::from_bytes(
        signature
            .try_into()
            .map_err(|_| CoreV02Reject::ProfileUnsupported)?,
    );
    let sig_structure = cose_signature_structure(bytes(&fields[0])?, payload)?;
    key.verify_strict(&sig_structure, &signature)
        .map_err(|_| CoreV02Reject::GrantInvalid)?;
    Ok(ValidatedRouteGrant {
        issuer_kid: protected.kid,
        payload: payload.to_vec(),
    })
}

struct ProtectedHeader {
    kid: Vec<u8>,
}

fn decode_protected_header(wire: &[u8]) -> Result<ProtectedHeader, CoreV02Reject> {
    if wire.is_empty() || wire.len() > 256 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let mut decoder = Decoder::new(wire, CoreV02Limits::default());
    let root = decoder.node(0)?;
    if decoder.position != wire.len() {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let map = map(&root)?;
    if map.len() != 2
        || uint(&map[0].0)? != 1
        || uint(&map[1].0)? != 4
        || nint(required(map, 1)?)? != -8
    {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let kid = bytes(required(map, 4)?)?;
    if kid.is_empty() || kid.len() > 64 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    Ok(ProtectedHeader { kid: kid.to_vec() })
}

fn cose_signature_structure(protected: &[u8], payload: &[u8]) -> Result<Vec<u8>, CoreV02Reject> {
    let mut wire = Vec::with_capacity(32 + protected.len() + payload.len());
    wire.push(0x84);
    encode_text(&mut wire, "Signature1")?;
    encode_bytes(&mut wire, protected)?;
    encode_bytes(&mut wire, &[])?;
    encode_bytes(&mut wire, payload)?;
    Ok(wire)
}

fn encode_text(target: &mut Vec<u8>, value: &str) -> Result<(), CoreV02Reject> {
    encode_major_argument(target, 3, value.len() as u64)?;
    target.extend_from_slice(value.as_bytes());
    Ok(())
}

fn encode_bytes(target: &mut Vec<u8>, value: &[u8]) -> Result<(), CoreV02Reject> {
    encode_major_argument(target, 2, value.len() as u64)?;
    target.extend_from_slice(value);
    Ok(())
}

fn encode_major_argument(target: &mut Vec<u8>, major: u8, value: u64) -> Result<(), CoreV02Reject> {
    let initial = major << 5;
    match value {
        0..=23 => target.push(initial | value as u8),
        24..=0xff => target.extend_from_slice(&[initial | 24, value as u8]),
        0x100..=0xffff => target.extend_from_slice(&[
            initial | 25,
            (value as u16).to_be_bytes()[0],
            (value as u16).to_be_bytes()[1],
        ]),
        0x1_0000..=0xffff_ffff => target.extend_from_slice(&[
            initial | 26,
            (value as u32).to_be_bytes()[0],
            (value as u32).to_be_bytes()[1],
            (value as u32).to_be_bytes()[2],
            (value as u32).to_be_bytes()[3],
        ]),
        _ => {
            target.push(initial | 27);
            target.extend_from_slice(&value.to_be_bytes());
        }
    }
    Ok(())
}

impl CoreV02Envelope {
    pub fn message_type(&self) -> CoreV02MessageType {
        self.message_type
    }

    /// The accepted deterministic bytes are retained verbatim.  This avoids a
    /// second serializer becoming a source of wire drift; outbound creation is
    /// added only with the later state-machine layer.
    pub fn encode(&self) -> Vec<u8> {
        self.wire.clone()
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum Node {
    Uint(u64),
    Nint(i64),
    Bytes(Vec<u8>),
    Text(String),
    Array(Vec<Node>),
    Map(Vec<(Node, Node)>),
    Bool(bool),
    Null,
}

pub fn decode_control_envelope(
    bytes: &[u8],
    limits: CoreV02Limits,
) -> Result<CoreV02Envelope, CoreV02Reject> {
    if bytes.is_empty() || bytes.len() > limits.max_frame_bytes {
        return Err(CoreV02Reject::OverCapacity);
    }
    let mut decoder = Decoder::new(bytes, limits);
    let root = decoder.node(0)?;
    if decoder.position != bytes.len() {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let envelope = map(&root)?;
    let protocol_version = uint(required(envelope, 0)?)?;
    if protocol_version != 2 {
        return Err(if protocol_version == 1 {
            CoreV02Reject::Downgrade
        } else {
            CoreV02Reject::ProfileUnsupported
        });
    }
    let message_type = message_type(uint(required(envelope, 1)?)?)?;
    bytes_exact(required(envelope, 2)?, 16)?;
    bytes_exact(required(envelope, 3)?, 16)?;
    if uint(required(envelope, 4)?)? == 0 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    let body = map(required(envelope, 5)?)?;
    ensure_envelope_keys(envelope)?;
    validate_body(message_type, body)?;
    Ok(CoreV02Envelope {
        message_type,
        wire: bytes.to_vec(),
    })
}

fn ensure_envelope_keys(entries: &[(Node, Node)]) -> Result<(), CoreV02Reject> {
    for (key, _) in entries {
        let key = uint(key)?;
        if key > 6 {
            return Err(CoreV02Reject::ProfileUnsupported);
        }
    }
    for required_key in 0..=5 {
        required(entries, required_key)?;
    }
    if entries.len() == 7 {
        let critical = array(required(entries, 6)?)?;
        if critical.is_empty() || critical.len() > 32 {
            return Err(CoreV02Reject::ProfileUnsupported);
        }
        // Core v0.2 currently recognizes no extension.  A non-empty critical
        // list is therefore always fail-closed, preserving D6 semantics.
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    if entries.len() != 6 {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    Ok(())
}

fn validate_body(
    message_type: CoreV02MessageType,
    body: &[(Node, Node)],
) -> Result<(), CoreV02Reject> {
    match message_type {
        CoreV02MessageType::ClientHello => {
            exact_keys(body, 7)?;
            exact_uint(body, 0, 1)?;
            for key in 1..=4 {
                ascii_id(required(body, key)?)?;
            }
            bytes_exact(required(body, 5)?, 32)?;
            bytes_exact(required(body, 6)?, 32)?;
            timestamp(required(body, 7)?)?;
        }
        CoreV02MessageType::EdgeHello => {
            exact_keys(body, 6)?;
            exact_uint(body, 0, 1)?;
            ascii_id(required(body, 1)?)?;
            ascii_id(required(body, 2)?)?;
            bytes_exact(required(body, 3)?, 32)?;
            bytes_exact(required(body, 4)?, 32)?;
            bytes_exact(required(body, 5)?, 32)?;
            timestamp(required(body, 6)?)?;
        }
        CoreV02MessageType::RouteOpen => {
            exact_keys(body, 7)?;
            exact_uint(body, 0, 1)?;
            bytes_exact(required(body, 1)?, 16)?;
            let grant = bytes(required(body, 2)?)?;
            if grant.is_empty() || grant.len() > 32_768 {
                return Err(CoreV02Reject::ProfileUnsupported);
            }
            bytes_exact(required(body, 3)?, 32)?;
            if text(required(body, 4)?)? != "tcp" {
                return Err(CoreV02Reject::ProfileUnsupported);
            }
            port(required(body, 5)?)?;
            timestamp(required(body, 6)?)?;
            bytes_exact(required(body, 7)?, 64)?;
        }
        CoreV02MessageType::RouteAccept => {
            exact_keys(body, 4)?;
            exact_uint(body, 0, 1)?;
            bytes_exact(required(body, 1)?, 16)?;
            bytes_exact(required(body, 2)?, 16)?;
            bytes_exact(required(body, 3)?, 32)?;
            timestamp(required(body, 4)?)?;
        }
        CoreV02MessageType::RouteReject => validate_reject_body(body)?,
        CoreV02MessageType::StreamOpen => {
            exact_keys(body, 6)?;
            exact_uint(body, 0, 1)?;
            let stream_id = uint(required(body, 1)?)?;
            if stream_id < 4 || stream_id % 4 != 0 || stream_id > 4_611_686_018_427_387_903 {
                return Err(CoreV02Reject::ProfileUnsupported);
            }
            bytes_exact(required(body, 2)?, 16)?;
            bytes_exact(required(body, 3)?, 16)?;
            bytes_exact(required(body, 4)?, 32)?;
            if text(required(body, 5)?)? != "tcp" {
                return Err(CoreV02Reject::ProfileUnsupported);
            }
            port(required(body, 6)?)?;
        }
        CoreV02MessageType::StreamAccept => {
            exact_keys(body, 4)?;
            exact_uint(body, 0, 1)?;
            let stream_id = uint(required(body, 1)?)?;
            if stream_id < 4 || stream_id % 4 != 0 || stream_id > 4_611_686_018_427_387_903 {
                return Err(CoreV02Reject::ProfileUnsupported);
            }
            bytes_exact(required(body, 2)?, 16)?;
            bytes_exact(required(body, 3)?, 16)?;
            timestamp(required(body, 4)?)?;
        }
        CoreV02MessageType::StreamReject => validate_reject_body(body)?,
    }
    Ok(())
}

fn validate_reject_body(body: &[(Node, Node)]) -> Result<(), CoreV02Reject> {
    exact_keys(body, 4)?;
    exact_uint(body, 0, 1)?;
    bytes_exact(required(body, 1)?, 16)?;
    bytes_exact(required(body, 2)?, 16)?;
    bytes_exact(required(body, 3)?, 32)?;
    map(required(body, 4)?)?;
    Ok(())
}

fn exact_keys(entries: &[(Node, Node)], maximum: u64) -> Result<(), CoreV02Reject> {
    if entries.len() != (maximum + 1) as usize {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    for key in 0..=maximum {
        required(entries, key)?;
    }
    for (key, _) in entries {
        if uint(key)? > maximum {
            return Err(CoreV02Reject::ProfileUnsupported);
        }
    }
    Ok(())
}

fn required(entries: &[(Node, Node)], wanted: u64) -> Result<&Node, CoreV02Reject> {
    entries
        .iter()
        .find_map(|(key, value)| (uint(key).ok() == Some(wanted)).then_some(value))
        .ok_or(CoreV02Reject::ProfileUnsupported)
}

fn map(node: &Node) -> Result<&[(Node, Node)], CoreV02Reject> {
    match node {
        Node::Map(value) => Ok(value),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

fn array(node: &Node) -> Result<&[Node], CoreV02Reject> {
    match node {
        Node::Array(value) => Ok(value),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

fn uint(node: &Node) -> Result<u64, CoreV02Reject> {
    match node {
        Node::Uint(value) => Ok(*value),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

fn nint(node: &Node) -> Result<i64, CoreV02Reject> {
    match node {
        Node::Nint(value) => Ok(*value),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

fn bytes(node: &Node) -> Result<&[u8], CoreV02Reject> {
    match node {
        Node::Bytes(value) => Ok(value),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

fn bytes_exact(node: &Node, wanted: usize) -> Result<(), CoreV02Reject> {
    (bytes(node)?.len() == wanted)
        .then_some(())
        .ok_or(CoreV02Reject::ProfileUnsupported)
}

fn text(node: &Node) -> Result<&str, CoreV02Reject> {
    match node {
        Node::Text(value) => Ok(value),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

fn ascii_id(node: &Node) -> Result<(), CoreV02Reject> {
    let value = text(node)?;
    if value.is_empty()
        || value.len() > 64
        || !value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'-')
        })
    {
        return Err(CoreV02Reject::ProfileUnsupported);
    }
    Ok(())
}

fn timestamp(node: &Node) -> Result<(), CoreV02Reject> {
    (uint(node)? <= 253_402_300_799)
        .then_some(())
        .ok_or(CoreV02Reject::ProfileUnsupported)
}

fn port(node: &Node) -> Result<(), CoreV02Reject> {
    let value = uint(node)?;
    (value != 0 && value <= 65_535)
        .then_some(())
        .ok_or(CoreV02Reject::ProfileUnsupported)
}

fn exact_uint(entries: &[(Node, Node)], key: u64, wanted: u64) -> Result<(), CoreV02Reject> {
    (uint(required(entries, key)?)? == wanted)
        .then_some(())
        .ok_or(CoreV02Reject::ProfileUnsupported)
}

fn message_type(value: u64) -> Result<CoreV02MessageType, CoreV02Reject> {
    match value {
        1 => Ok(CoreV02MessageType::ClientHello),
        2 => Ok(CoreV02MessageType::EdgeHello),
        3 => Ok(CoreV02MessageType::RouteOpen),
        4 => Ok(CoreV02MessageType::RouteAccept),
        5 => Ok(CoreV02MessageType::RouteReject),
        6 => Ok(CoreV02MessageType::StreamOpen),
        7 => Ok(CoreV02MessageType::StreamAccept),
        8 => Ok(CoreV02MessageType::StreamReject),
        _ => Err(CoreV02Reject::ProfileUnsupported),
    }
}

struct Decoder<'a> {
    bytes: &'a [u8],
    position: usize,
    limits: CoreV02Limits,
}

impl<'a> Decoder<'a> {
    fn new(bytes: &'a [u8], limits: CoreV02Limits) -> Self {
        Self {
            bytes,
            position: 0,
            limits,
        }
    }

    fn node(&mut self, depth: usize) -> Result<Node, CoreV02Reject> {
        if depth > self.limits.max_depth {
            return Err(CoreV02Reject::OverCapacity);
        }
        let initial = self.take()?;
        let major = initial >> 5;
        let additional = initial & 0x1f;
        let value = self.argument(additional)?;
        match major {
            0 => Ok(Node::Uint(value)),
            1 => value
                .try_into()
                .ok()
                .and_then(|value: i64| value.checked_add(1))
                .and_then(|value| value.checked_neg())
                .map(Node::Nint)
                .ok_or(CoreV02Reject::ProfileUnsupported),
            2 => Ok(Node::Bytes(self.take_slice(value as usize)?.to_vec())),
            3 => {
                let slice = self.take_slice(value as usize)?;
                let text = std::str::from_utf8(slice)
                    .map_err(|_| CoreV02Reject::ProfileUnsupported)?
                    .to_owned();
                Ok(Node::Text(text))
            }
            4 => self.array(value as usize, depth + 1),
            5 => self.map(value as usize, depth + 1),
            6 => Err(CoreV02Reject::ProfileUnsupported),
            7 if additional == 20 => Ok(Node::Bool(false)),
            7 if additional == 21 => Ok(Node::Bool(true)),
            7 if additional == 22 => Ok(Node::Null),
            _ => Err(CoreV02Reject::ProfileUnsupported),
        }
    }

    fn array(&mut self, length: usize, depth: usize) -> Result<Node, CoreV02Reject> {
        if length > self.limits.max_array_items {
            return Err(CoreV02Reject::OverCapacity);
        }
        let mut values = Vec::with_capacity(length);
        for _ in 0..length {
            values.push(self.node(depth)?);
        }
        Ok(Node::Array(values))
    }

    fn map(&mut self, length: usize, depth: usize) -> Result<Node, CoreV02Reject> {
        if length > self.limits.max_map_pairs {
            return Err(CoreV02Reject::OverCapacity);
        }
        let mut values = Vec::with_capacity(length);
        let mut prior_key: Option<Vec<u8>> = None;
        for _ in 0..length {
            let start = self.position;
            let key = self.node(depth)?;
            let encoded_key = self.bytes[start..self.position].to_vec();
            if prior_key
                .as_ref()
                .is_some_and(|prior| prior >= &encoded_key)
            {
                return Err(CoreV02Reject::ProfileUnsupported);
            }
            prior_key = Some(encoded_key);
            values.push((key, self.node(depth)?));
        }
        Ok(Node::Map(values))
    }

    fn argument(&mut self, additional: u8) -> Result<u64, CoreV02Reject> {
        match additional {
            0..=23 => Ok(u64::from(additional)),
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
            _ => Err(CoreV02Reject::ProfileUnsupported),
        }
    }

    fn preferred(&self, value: u64, minimum: u64) -> Result<u64, CoreV02Reject> {
        if value < minimum {
            return Err(CoreV02Reject::ProfileUnsupported);
        }
        Ok(value)
    }

    fn take(&mut self) -> Result<u8, CoreV02Reject> {
        let value = *self
            .bytes
            .get(self.position)
            .ok_or(CoreV02Reject::ProfileUnsupported)?;
        self.position += 1;
        Ok(value)
    }

    fn take_slice(&mut self, length: usize) -> Result<&'a [u8], CoreV02Reject> {
        let end = self
            .position
            .checked_add(length)
            .ok_or(CoreV02Reject::OverCapacity)?;
        let slice = self
            .bytes
            .get(self.position..end)
            .ok_or(CoreV02Reject::ProfileUnsupported)?;
        self.position = end;
        Ok(slice)
    }
}
