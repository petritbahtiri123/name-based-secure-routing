use sha2::{Digest, Sha256};

use crate::core_v02::{RouteGrantIssuer, validate_ed25519_sign1};

const SOURCE_PURPOSE: &str = "nbsr-federation-source-admission";
const DESTINATION_PURPOSE: &str = "nbsr-federation-destination-admission";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LocalFederationAdmissionAuthorities {
    pub(crate) source_kid: Vec<u8>,
    pub(crate) source_public_key: [u8; 32],
    pub(crate) destination_kid: Vec<u8>,
    pub(crate) destination_public_key: [u8; 32],
}

impl LocalFederationAdmissionAuthorities {
    pub fn new(
        source_kid: Vec<u8>,
        source_public_key: [u8; 32],
        destination_kid: Vec<u8>,
        destination_public_key: [u8; 32],
    ) -> Result<Self, FederationReject> {
        if source_kid.is_empty()
            || source_kid.len() > 64
            || destination_kid.is_empty()
            || destination_kid.len() > 64
            || source_kid == destination_kid
            || source_public_key == destination_public_key
        {
            return Err(FederationReject::UntrustedAttestation);
        }
        Ok(Self {
            source_kid,
            source_public_key,
            destination_kid,
            destination_public_key,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LocalFederationAdmissionAttestations {
    pub source: Vec<u8>,
    pub destination: Vec<u8>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FederationReject {
    InvalidBinding,
    InvalidDependencyState,
    NotYetValid,
    Expired,
    Revoked,
    UnsupportedProfile,
    UntrustedAttestation,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct VerifiedFederationAuthorization {
    source_operator_id: [u8; 32],
    destination_operator_id: [u8; 32],
    service_id: [u8; 32],
    canonical_name: String,
    transport: String,
    port: u16,
    route_grant_digest: [u8; 32],
    federation_context_digest: [u8; 32],
    effective_at: u64,
    valid_until: u64,
    affected_generation: u64,
    affected_sequence: u64,
    dependencies: Vec<[u8; 32]>,
    source_operator_text: String,
    destination_operator_text: String,
}

impl VerifiedFederationAuthorization {
    pub(crate) fn source_operator_text(&self) -> &str {
        &self.source_operator_text
    }
    pub(crate) fn destination_operator_text(&self) -> &str {
        &self.destination_operator_text
    }
    pub(crate) fn canonical_name(&self) -> &str {
        &self.canonical_name
    }
    pub(crate) fn transport(&self) -> &str {
        &self.transport
    }
    pub(crate) fn port(&self) -> u16 {
        self.port
    }
    pub(crate) fn route_grant_digest(&self) -> &[u8; 32] {
        &self.route_grant_digest
    }
    pub(crate) fn federation_context_digest(&self) -> &[u8; 32] {
        &self.federation_context_digest
    }
    pub(crate) fn effective_at(&self) -> u64 {
        self.effective_at
    }
    pub(crate) fn valid_until(&self) -> u64 {
        self.valid_until
    }
}

pub(crate) fn verify_local_admission_attestations(
    attestations: &LocalFederationAdmissionAttestations,
    authorities: &LocalFederationAdmissionAuthorities,
    now: u64,
) -> Result<VerifiedFederationAuthorization, FederationReject> {
    if authorities.source_kid.is_empty()
        || authorities.destination_kid.is_empty()
        || authorities.source_kid == authorities.destination_kid
        || authorities.source_public_key == authorities.destination_public_key
    {
        return Err(FederationReject::UntrustedAttestation);
    }
    let source = verified_payload(
        &attestations.source,
        &authorities.source_kid,
        authorities.source_public_key,
    )?;
    let destination = verified_payload(
        &attestations.destination,
        &authorities.destination_kid,
        authorities.destination_public_key,
    )?;
    let source = parse_payload(&source, SOURCE_PURPOSE)?;
    let destination = parse_payload(&destination, DESTINATION_PURPOSE)?;
    if source != destination {
        return Err(FederationReject::InvalidBinding);
    }
    if now < source.effective_at {
        return Err(FederationReject::NotYetValid);
    }
    if now > source.valid_until {
        return Err(FederationReject::Expired);
    }
    if source.dependencies.is_empty()
        || source.dependencies.len() > 256
        || !source.dependencies.windows(2).all(|p| p[0] < p[1])
    {
        return Err(FederationReject::InvalidDependencyState);
    }
    if source.source_operator_id == source.destination_operator_id
        || source.port == 0
        || source.effective_at >= source.valid_until
        || source.affected_generation == 0
        || source.affected_sequence == 0
        || !matches!(source.transport.as_str(), "tcp" | "udp")
        || !valid_canonical_name(&source.canonical_name)
        || service_id(&source.source_operator_id, &source.canonical_name) != source.service_id
    {
        return Err(FederationReject::InvalidBinding);
    }
    Ok(VerifiedFederationAuthorization {
        source_operator_text: operator_text(&source.source_operator_id),
        destination_operator_text: operator_text(&source.destination_operator_id),
        source_operator_id: source.source_operator_id,
        destination_operator_id: source.destination_operator_id,
        service_id: source.service_id,
        canonical_name: source.canonical_name,
        transport: source.transport,
        port: source.port,
        route_grant_digest: source.route_grant_digest,
        federation_context_digest: source.federation_context_digest,
        effective_at: source.effective_at,
        valid_until: source.valid_until,
        affected_generation: source.affected_generation,
        affected_sequence: source.affected_sequence,
        dependencies: source.dependencies,
    })
}

fn verified_payload(wire: &[u8], kid: &[u8], key: [u8; 32]) -> Result<Vec<u8>, FederationReject> {
    let issuer = RouteGrantIssuer {
        kid: kid.to_vec(),
        public_key: key,
    };
    validate_ed25519_sign1(wire, &[issuer])
        .map(|v| v.payload)
        .map_err(|_| FederationReject::UntrustedAttestation)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Payload {
    source_operator_id: [u8; 32],
    destination_operator_id: [u8; 32],
    service_id: [u8; 32],
    canonical_name: String,
    transport: String,
    port: u16,
    route_grant_digest: [u8; 32],
    federation_context_digest: [u8; 32],
    effective_at: u64,
    valid_until: u64,
    affected_generation: u64,
    affected_sequence: u64,
    dependencies: Vec<[u8; 32]>,
}

fn parse_payload(wire: &[u8], purpose: &str) -> Result<Payload, FederationReject> {
    let mut c = Cursor { wire, pos: 0 };
    if c.map_len()? != 15 {
        return Err(FederationReject::InvalidBinding);
    }
    c.key(0)?;
    if c.uint()? != 1 {
        return Err(FederationReject::UnsupportedProfile);
    }
    c.key(1)?;
    if c.text()? != purpose {
        return Err(FederationReject::UntrustedAttestation);
    }
    c.key(2)?;
    let source_operator_id = c.bytes32()?;
    c.key(3)?;
    let destination_operator_id = c.bytes32()?;
    c.key(4)?;
    let service_id = c.bytes32()?;
    c.key(5)?;
    let canonical_name = c.text()?.to_owned();
    c.key(6)?;
    let protocol = c.uint()?;
    let transport = match protocol {
        6 => "tcp",
        17 => "udp",
        _ => return Err(FederationReject::InvalidBinding),
    }
    .to_owned();
    c.key(7)?;
    let port = u16::try_from(c.uint()?).map_err(|_| FederationReject::InvalidBinding)?;
    c.key(8)?;
    let route_grant_digest = c.bytes32()?;
    c.key(9)?;
    let federation_context_digest = c.bytes32()?;
    c.key(10)?;
    let effective_at = c.uint()?;
    c.key(11)?;
    let valid_until = c.uint()?;
    c.key(12)?;
    let affected_generation = c.uint()?;
    c.key(13)?;
    let affected_sequence = c.uint()?;
    c.key(14)?;
    let count = c.array_len()?;
    if count > 256 {
        return Err(FederationReject::InvalidDependencyState);
    }
    let mut dependencies = Vec::with_capacity(count);
    for _ in 0..count {
        dependencies.push(c.bytes32()?);
    }
    if c.pos != wire.len() {
        return Err(FederationReject::InvalidBinding);
    }
    Ok(Payload {
        source_operator_id,
        destination_operator_id,
        service_id,
        canonical_name,
        transport,
        port,
        route_grant_digest,
        federation_context_digest,
        effective_at,
        valid_until,
        affected_generation,
        affected_sequence,
        dependencies,
    })
}

struct Cursor<'a> {
    wire: &'a [u8],
    pos: usize,
}
impl<'a> Cursor<'a> {
    fn head(&mut self, major: u8) -> Result<u64, FederationReject> {
        let b = *self
            .wire
            .get(self.pos)
            .ok_or(FederationReject::InvalidBinding)?;
        self.pos += 1;
        if b >> 5 != major {
            return Err(FederationReject::InvalidBinding);
        };
        let n = b & 31;
        match n {
            0..=23 => Ok(u64::from(n)),
            24 => {
                let v = *self
                    .wire
                    .get(self.pos)
                    .ok_or(FederationReject::InvalidBinding)?;
                self.pos += 1;
                if v < 24 {
                    return Err(FederationReject::InvalidBinding);
                };
                Ok(u64::from(v))
            }
            25 => {
                let s = self.take(2)?;
                let v = u16::from_be_bytes([s[0], s[1]]);
                if v <= 255 {
                    return Err(FederationReject::InvalidBinding);
                };
                Ok(u64::from(v))
            }
            26 => {
                let s = self.take(4)?;
                let v = u32::from_be_bytes(s.try_into().unwrap());
                if v <= 65535 {
                    return Err(FederationReject::InvalidBinding);
                };
                Ok(u64::from(v))
            }
            27 => {
                let s = self.take(8)?;
                let v = u64::from_be_bytes(s.try_into().unwrap());
                if v <= u64::from(u32::MAX) {
                    return Err(FederationReject::InvalidBinding);
                };
                Ok(v)
            }
            _ => Err(FederationReject::InvalidBinding),
        }
    }
    fn take(&mut self, n: usize) -> Result<&'a [u8], FederationReject> {
        let end = self
            .pos
            .checked_add(n)
            .ok_or(FederationReject::InvalidBinding)?;
        let s = self
            .wire
            .get(self.pos..end)
            .ok_or(FederationReject::InvalidBinding)?;
        self.pos = end;
        Ok(s)
    }
    fn uint(&mut self) -> Result<u64, FederationReject> {
        self.head(0)
    }
    fn map_len(&mut self) -> Result<usize, FederationReject> {
        usize::try_from(self.head(5)?).map_err(|_| FederationReject::InvalidBinding)
    }
    fn array_len(&mut self) -> Result<usize, FederationReject> {
        usize::try_from(self.head(4)?).map_err(|_| FederationReject::InvalidBinding)
    }
    fn key(&mut self, k: u64) -> Result<(), FederationReject> {
        if self.uint()? == k {
            Ok(())
        } else {
            Err(FederationReject::InvalidBinding)
        }
    }
    fn text(&mut self) -> Result<&'a str, FederationReject> {
        let n = usize::try_from(self.head(3)?).map_err(|_| FederationReject::InvalidBinding)?;
        std::str::from_utf8(self.take(n)?).map_err(|_| FederationReject::InvalidBinding)
    }
    fn bytes32(&mut self) -> Result<[u8; 32], FederationReject> {
        if self.head(2)? != 32 {
            return Err(FederationReject::InvalidBinding);
        };
        self.take(32)?
            .try_into()
            .map_err(|_| FederationReject::InvalidBinding)
    }
}

fn valid_canonical_name(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 255
        && v.is_ascii()
        && v == v.to_ascii_lowercase()
        && !v.ends_with('.')
        && v.split('.').all(|l| {
            !l.is_empty()
                && l.len() <= 63
                && l.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                && l.as_bytes().first() != Some(&b'-')
                && l.as_bytes().last() != Some(&b'-')
        })
}
fn service_id(operator_id: &[u8; 32], name: &str) -> [u8; 32] {
    let mut d = Sha256::new();
    d.update(b"NBSR-FEDERATION-SERVICE-ID-v1\0");
    d.update(operator_id);
    d.update((name.len() as u16).to_be_bytes());
    d.update(name.as_bytes());
    d.finalize().into()
}
fn operator_text(operator_id: &[u8; 32]) -> String {
    const C: &[u8; 32] = b"qpzry9x8gf2tvdw0s3jn54khce6mua7l";
    let mut data = Vec::with_capacity(52);
    let (mut a, mut bits) = (0u32, 0u8);
    for byte in operator_id {
        a = (a << 8) | u32::from(*byte);
        bits += 8;
        while bits >= 5 {
            bits -= 5;
            data.push(((a >> bits) & 31) as u8)
        }
    }
    if bits != 0 {
        data.push(((a << (5 - bits)) & 31) as u8)
    }
    let mut values = vec![3, 3, 3, 3, 0, 14, 2, 19, 18];
    values.extend_from_slice(&data);
    values.extend_from_slice(&[0; 6]);
    let mut p = 1u32;
    for v in values {
        let top = p >> 25;
        p = ((p & 0x1ff_ffff) << 5) ^ u32::from(v);
        for (i, g) in [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
            .iter()
            .enumerate()
        {
            if ((top >> i) & 1) != 0 {
                p ^= g
            }
        }
    }
    p ^= 0x2bc830a3;
    let checksum = (0..6).map(|i| ((p >> (5 * (5 - i))) & 31) as u8);
    let encoded: String = data
        .into_iter()
        .chain(checksum)
        .map(|v| C[v as usize] as char)
        .collect();
    format!("nbsr1{encoded}")
}
