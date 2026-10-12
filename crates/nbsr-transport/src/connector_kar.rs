//! Isolated test-only genesis KAR checks relative to supplied test trust.
//! No production export, authority conversion, ownership, clocks or persistent floors.
#![cfg(test)]
use crate::{
    codec::{self, Result, Value as V, get, map, uint},
    signature,
};

const MAX_TIME: u64 = 253_402_300_799;
#[derive(Clone)]
struct SuppliedTestRoot {
    operator: [u8; 32],
    kid: Vec<u8>,
    key: [u8; 32],
    purpose: u64,
    lifecycle: u64,
    generation: u64,
    sequence: u64,
    not_before: u64,
    expires: u64,
    revoked: bool,
}
#[derive(Clone)]
struct ExpectedKey {
    operator: [u8; 32],
    kid: Vec<u8>,
    key: [u8; 32],
    purpose: u64,
    // Explicit fixture context, not an authenticated revocation source.
    terminal_ids: Vec<Vec<u8>>,
}
struct VerifiedFixtureKar {
    _payload: Vec<u8>,
}

fn require(ok: bool, why: &'static str) -> Result<()> {
    if ok { Ok(()) } else { Err(why) }
}
fn b(value: &V, min: usize, max: usize) -> Result<&[u8]> {
    match value {
        V::Bytes(x) if (min..=max).contains(&x.len()) => Ok(x),
        _ => Err("KAR byte string bounds"),
    }
}
fn reference(v: &V) -> Result<()> {
    let m = map(v)?;
    require(
        m.keys().copied().collect::<Vec<_>>() == [1, 2, 3, 4],
        "authority reference fields",
    )?;
    require((1..=14).contains(&uint(get(m, 1)?)?), "authority class")?;
    b(get(m, 2)?, 1, 64)?;
    if get(m, 3)? != &V::Null {
        b(get(m, 3)?, 1, 64)?;
    }
    if get(m, 4)? != &V::Null {
        b(get(m, 4)?, 32, 32)?;
    }
    Ok(())
}
fn extensions(v: &V) -> Result<()> {
    let m = map(v)?;
    require(m.len() <= 16, "extension count")?;
    for (id, value) in m {
        require((1000..=65535).contains(id), "extension id")?;
        let x = map(value)?;
        require(
            x.keys().copied().collect::<Vec<_>>() == [1, 2, 3],
            "extension fields",
        )?;
        require(
            (1..=65535).contains(&uint(get(x, 1)?)?),
            "extension version",
        )?;
        require(
            get(x, 2)? == &V::Bool(false),
            "unknown critical or malformed extension",
        )?;
        b(get(x, 3)?, 0, 4096)?;
    }
    Ok(())
}
// Private semantic helper never constructs the checked-signature result.
// Tests exercise it separately because no authorized signed positive exists.
fn semantics(
    payload: &[u8],
    root: &SuppliedTestRoot,
    expected: &ExpectedKey,
    now: u64,
) -> Result<()> {
    require(payload.len() <= 32768, "KAR payload bound")?;
    let value = codec::decode_value(payload)?;
    let m = map(&value)?;
    let required = [1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39];
    require(
        required.iter().all(|k| m.contains_key(k))
            && m.keys().all(|k| required.contains(k) || *k == 31),
        "genesis KAR fields",
    )?;
    require(
        uint(get(m, 1)?)? == 2 && uint(get(m, 2)?)? == 1,
        "KAR object and version",
    )?;
    require(
        uint(get(m, 4)?)? == 1 && uint(get(m, 5)?)? == 1,
        "genesis lineage only",
    )?;
    reference(get(m, 3)?)?; // Existing issuer schema, no additional issuer/root join.
    reference(get(m, 37)?)?;
    if let Some(v) = m.get(&31) {
        extensions(v)?;
    }
    let start = uint(get(m, 6)?)?;
    let expiry = uint(get(m, 7)?)?;
    require(
        start < expiry && expiry <= MAX_TIME && start <= now && now <= expiry,
        "KAR validity",
    )?;
    require(
        root.purpose == 1 && root.lifecycle == 2 && !root.revoked,
        "identity-root active purpose required",
    )?;
    require(
        root.generation > 0 && root.sequence > 0 && (1..=64).contains(&root.kid.len()),
        "root identity and lineage",
    )?;
    require(
        root.not_before < root.expires
            && root.expires <= MAX_TIME
            && root.not_before <= now
            && now <= root.expires,
        "root validity",
    )?;
    require(
        b(get(m, 32)?, 32, 32)? == root.operator && expected.operator == root.operator,
        "operator binding",
    )?;
    let authorizer = map(get(m, 37)?)?;
    require(
        uint(get(authorizer, 1)?)? == 1
            && b(get(authorizer, 2)?, 32, 32)? == root.operator
            && b(get(authorizer, 3)?, 1, 64)? == root.kid
            && b(get(authorizer, 4)?, 32, 32)? == root.operator,
        "exact root authorizer",
    )?;
    let kid = b(get(m, 33)?, 1, 64)?;
    require(
        kid == expected.kid && b(get(m, 34)?, 32, 32)? == expected.key,
        "expected child identity",
    )?;
    let purpose = uint(get(m, 35)?)?;
    require(
        (1..=16).contains(&purpose) && purpose == expected.purpose,
        "exact child purpose",
    )?;
    require(
        uint(get(m, 36)?)? == 2 && get(m, 38)? == &V::Bool(false) && get(m, 39)? == &V::Null,
        "active unrevoked child required",
    )?;
    require(
        !expected.terminal_ids.iter().any(|x| x == kid),
        "terminal key ID",
    )?;
    Ok(())
}

fn verify_genesis(
    wire: &[u8],
    expected_payload: &[u8],
    root: &SuppliedTestRoot,
    expected: &ExpectedKey,
    now: u64,
) -> Result<VerifiedFixtureKar> {
    let signed = signature::verify_exact(wire, expected_payload, &root.kid, &root.key)?;
    semantics(signed.payload(), root, expected, now)?;
    Ok(VerifiedFixtureKar {
        _payload: signed.payload().to_vec(),
    })
}

#[path = "../tests/support/connector_kar.rs"]
mod tests;
