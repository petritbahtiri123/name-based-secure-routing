//! Pure Service Channel context and fixture-secret exporter conformance logic.
//!
//! This module does not access a live TLS connection or exporter secret. The
//! caller must supply an explicit fixture secret to the conformance function.

use core::fmt;

use sha2::{Digest, Sha256};

const CONTEXT_PROFILE: &str = "NBSR-SERVICE-CHANNEL-CONTEXT-v2";
const EXPORTER_LABEL: &[u8] = b"EXPORTER-NBSR-Service-Channel-v2";
const EXPORTER_LENGTH: usize = 32;
const SHA256_BLOCK_LENGTH: usize = 64;
const SHA256_OUTPUT_LENGTH: usize = 32;

/// Immutable inputs to the frozen Core v0.2 Service Channel context.
///
/// `Debug` is intentionally not implemented because the context contains
/// nonces and binding values.
pub struct ServiceChannelContext<'a> {
    pub session_id: [u8; 16],
    pub source_edge_id: &'a str,
    pub destination_edge_id: &'a str,
    pub channel_id: [u8; 16],
    pub route_id: [u8; 16],
    pub route_grant_digest: [u8; 32],
    pub service_id: &'a str,
    pub transport: &'a str,
    pub port: u16,
    pub policy_hash: [u8; 32],
    pub client_nonce: [u8; 32],
    pub edge_nonce: [u8; 32],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ServiceChannelExporterError {
    InvalidSourceEdgeId,
    InvalidDestinationEdgeId,
    InvalidServiceId,
    InvalidTransport,
    InvalidPort,
    HkdfOutputLength,
    TlsLabelLength,
    TlsContextLength,
}

/// A derived Service Channel binding whose debug representation is redacted.
#[derive(Eq, PartialEq)]
pub struct ServiceChannelBinding([u8; EXPORTER_LENGTH]);

impl ServiceChannelBinding {
    pub fn as_bytes(&self) -> &[u8; EXPORTER_LENGTH] {
        &self.0
    }
}

impl fmt::Debug for ServiceChannelBinding {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ServiceChannelBinding([REDACTED])")
    }
}

fn valid_ascii_id(value: &str, maximum: usize) -> bool {
    !value.is_empty() && value.len() <= maximum && value.is_ascii()
}

fn validate_context(
    context: &ServiceChannelContext<'_>,
) -> Result<(), ServiceChannelExporterError> {
    if !valid_ascii_id(context.source_edge_id, 64) {
        return Err(ServiceChannelExporterError::InvalidSourceEdgeId);
    }
    if !valid_ascii_id(context.destination_edge_id, 64) {
        return Err(ServiceChannelExporterError::InvalidDestinationEdgeId);
    }
    if !valid_ascii_id(context.service_id, 255) {
        return Err(ServiceChannelExporterError::InvalidServiceId);
    }
    if !matches!(context.transport, "tcp" | "udp") {
        return Err(ServiceChannelExporterError::InvalidTransport);
    }
    if context.port == 0 {
        return Err(ServiceChannelExporterError::InvalidPort);
    }
    Ok(())
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

fn encode_bytes(target: &mut Vec<u8>, value: &[u8]) {
    encode_argument(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn encode_text(target: &mut Vec<u8>, value: &str) {
    encode_argument(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}

fn encode_uint(target: &mut Vec<u8>, value: u64) {
    encode_argument(target, 0, value);
}

/// Returns the preferred deterministic CBOR bytes for a validated context.
pub fn canonical_service_channel_context(
    context: &ServiceChannelContext<'_>,
) -> Result<Vec<u8>, ServiceChannelExporterError> {
    validate_context(context)?;
    let mut wire = Vec::with_capacity(384);
    encode_argument(&mut wire, 4, 14);
    encode_text(&mut wire, CONTEXT_PROFILE);
    encode_uint(&mut wire, 2);
    encode_bytes(&mut wire, &context.session_id);
    encode_text(&mut wire, context.source_edge_id);
    encode_text(&mut wire, context.destination_edge_id);
    encode_bytes(&mut wire, &context.channel_id);
    encode_bytes(&mut wire, &context.route_id);
    encode_bytes(&mut wire, &context.route_grant_digest);
    encode_text(&mut wire, context.service_id);
    encode_text(&mut wire, context.transport);
    encode_uint(&mut wire, u64::from(context.port));
    encode_bytes(&mut wire, &context.policy_hash);
    encode_bytes(&mut wire, &context.client_nonce);
    encode_bytes(&mut wire, &context.edge_nonce);
    Ok(wire)
}

fn hmac_sha256(key: &[u8], input: &[u8]) -> [u8; SHA256_OUTPUT_LENGTH] {
    let mut normalized_key = [0_u8; SHA256_BLOCK_LENGTH];
    if key.len() > SHA256_BLOCK_LENGTH {
        normalized_key[..SHA256_OUTPUT_LENGTH].copy_from_slice(&Sha256::digest(key));
    } else {
        normalized_key[..key.len()].copy_from_slice(key);
    }
    let mut inner_pad = [0x36_u8; SHA256_BLOCK_LENGTH];
    let mut outer_pad = [0x5c_u8; SHA256_BLOCK_LENGTH];
    for index in 0..SHA256_BLOCK_LENGTH {
        inner_pad[index] ^= normalized_key[index];
        outer_pad[index] ^= normalized_key[index];
    }
    let mut inner = Sha256::new();
    inner.update(inner_pad);
    inner.update(input);
    let inner_digest = inner.finalize();
    let mut outer = Sha256::new();
    outer.update(outer_pad);
    outer.update(inner_digest);
    outer.finalize().into()
}

fn hkdf_expand_sha256(
    secret: &[u8],
    info: &[u8],
    length: usize,
) -> Result<Vec<u8>, ServiceChannelExporterError> {
    if length > 255 * SHA256_OUTPUT_LENGTH {
        return Err(ServiceChannelExporterError::HkdfOutputLength);
    }
    let mut output = Vec::with_capacity(length);
    let mut previous = Vec::new();
    let blocks = length.div_ceil(SHA256_OUTPUT_LENGTH);
    for counter in 1..=blocks {
        let mut input = Vec::with_capacity(previous.len() + info.len() + 1);
        input.extend_from_slice(&previous);
        input.extend_from_slice(info);
        input.push(counter as u8);
        previous = hmac_sha256(secret, &input).to_vec();
        output.extend_from_slice(&previous);
    }
    output.truncate(length);
    Ok(output)
}

fn hkdf_expand_label(
    secret: &[u8],
    label: &[u8],
    context: &[u8],
    length: usize,
) -> Result<Vec<u8>, ServiceChannelExporterError> {
    let full_label_length = b"tls13 ".len() + label.len();
    if length > usize::from(u16::MAX) {
        return Err(ServiceChannelExporterError::HkdfOutputLength);
    }
    if full_label_length > usize::from(u8::MAX) {
        return Err(ServiceChannelExporterError::TlsLabelLength);
    }
    if context.len() > usize::from(u8::MAX) {
        return Err(ServiceChannelExporterError::TlsContextLength);
    }
    let mut info = Vec::with_capacity(4 + full_label_length + context.len());
    info.extend_from_slice(&(length as u16).to_be_bytes());
    info.push(full_label_length as u8);
    info.extend_from_slice(b"tls13 ");
    info.extend_from_slice(label);
    info.push(context.len() as u8);
    info.extend_from_slice(context);
    hkdf_expand_sha256(secret, &info, length)
}

/// Derives the frozen exporter value from an explicit conformance-fixture
/// exporter master secret. It never reads secret material from rustls or Quinn.
pub fn derive_service_channel_exporter_fixture(
    exporter_master_secret: &[u8; 32],
    context: &ServiceChannelContext<'_>,
) -> Result<ServiceChannelBinding, ServiceChannelExporterError> {
    let canonical_context = canonical_service_channel_context(context)?;
    let context_hash = Sha256::digest(&canonical_context);
    let empty_hash = Sha256::digest([]);
    let derived_secret = hkdf_expand_label(
        exporter_master_secret,
        EXPORTER_LABEL,
        &empty_hash,
        EXPORTER_LENGTH,
    )?;
    let exporter_value =
        hkdf_expand_label(&derived_secret, b"exporter", &context_hash, EXPORTER_LENGTH)?;
    Ok(ServiceChannelBinding(exporter_value.try_into().map_err(
        |_| ServiceChannelExporterError::HkdfOutputLength,
    )?))
}
