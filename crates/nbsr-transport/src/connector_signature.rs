//! Test-only signature primitive. No authority, registration or readiness API.
#![cfg(test)]
use ed25519_dalek::{Signature, VerifyingKey};

const MAX_BYTES: usize = 65536;
type Result<T> = std::result::Result<T, &'static str>;

pub struct CheckedSignature {
    payload: Vec<u8>,
}
impl CheckedSignature {
    pub fn payload(&self) -> &[u8] {
        &self.payload
    }
}
pub fn verify_exact(
    wire: &[u8],
    expected_payload: &[u8],
    kid: &[u8],
    public_key: &[u8; 32],
) -> Result<CheckedSignature> {
    if wire.len() > MAX_BYTES
        || expected_payload.len() > MAX_BYTES
        || !(1..=64).contains(&kid.len())
    {
        return Err("bounded signature input required");
    }
    let mut input = Input { wire, at: 0 };
    // Exact preferred tag 18 + fixed four-item array. No alternate tags,
    // detached payload, indefinite lengths, unprotected headers or trailing data.
    if input.take(2)? != [0xd2, 0x84] {
        return Err("tagged Sign1 required");
    }
    let protected = input.bstr()?;
    let mut expected_protected = vec![0xa2, 1, 0x27, 4]; // {1: -8, 4: kid}
    put_bstr(&mut expected_protected, kid);
    if protected != expected_protected || input.take(1)? != [0xa0] {
        return Err("exact protected headers and empty unprotected map required");
    }
    let payload = input.bstr()?;
    if payload != expected_payload {
        return Err("signature payload context mismatch");
    }
    let signature = input.bstr()?;
    if signature.len() != 64 || input.at != wire.len() {
        return Err("signature size or trailing data");
    }
    let mut signing_input = vec![0x84, 0x6a]; // ["Signature1", protected, h'', payload]
    signing_input.extend(b"Signature1");
    put_bstr(&mut signing_input, protected);
    put_bstr(&mut signing_input, &[]);
    put_bstr(&mut signing_input, payload);
    let key = VerifyingKey::from_bytes(public_key).map_err(|_| "invalid public key")?;
    let signature = Signature::from_slice(signature).map_err(|_| "invalid signature length")?;
    key.verify_strict(&signing_input, &signature)
        .map_err(|_| "invalid signature")?;
    // This result intentionally has no conversion to Authority, registration
    // receipts, semantic threshold evidence, events, owner state or readiness.
    // It does not parse/authorize the payload or authenticate the supplied key.
    Ok(CheckedSignature {
        payload: payload.to_vec(),
    })
}

struct Input<'a> {
    wire: &'a [u8],
    at: usize,
}
impl<'a> Input<'a> {
    fn take(&mut self, size: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(size).ok_or("length overflow")?;
        let data = self.wire.get(self.at..end).ok_or("truncated Sign1")?;
        self.at = end;
        Ok(data)
    }
    fn bstr(&mut self) -> Result<&'a [u8]> {
        let first = self.take(1)?[0];
        if first >> 5 != 2 {
            return Err("attached byte string required");
        }
        let length = match first & 31 {
            n @ 0..=23 => usize::from(n),
            24 => {
                let n = usize::from(self.take(1)?[0]);
                if n < 24 {
                    return Err("noncanonical length");
                }
                n
            }
            25 => {
                let n = usize::from(u16::from_be_bytes(self.take(2)?.try_into().unwrap()));
                if n <= 255 {
                    return Err("noncanonical length");
                }
                n
            }
            // Four/eight-byte lengths cannot fit a <=65536-byte envelope:
            // a preferred four-byte length is at least 65536 by itself.
            _ => return Err("overbound or noncanonical byte string"),
        };
        self.take(length)
    }
}
fn put_bstr(output: &mut Vec<u8>, value: &[u8]) {
    match value.len() {
        n @ 0..=23 => output.push(0x40 | n as u8),
        n @ 24..=255 => output.extend([0x58, n as u8]),
        n => {
            output.push(0x59);
            output.extend((n as u16).to_be_bytes());
        }
    }
    output.extend(value);
}
