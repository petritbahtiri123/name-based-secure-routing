//! Bounded test-only NOR/direct-delegation evidence, never an admission receipt.
//! No runtime export, provisioning, currentness, governance, or READY conversion.
use crate::{
    codec::{self, Value as V},
    kar::SuppliedTestRoot,
    signature,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

#[derive(Debug, PartialEq, Eq)]
pub enum Reject {
    Invalid(&'static str),
    Unsupported(&'static str),
}
impl From<&'static str> for Reject {
    fn from(s: &'static str) -> Self {
        Self::Invalid(s)
    }
}
type R<T> = Result<T, Reject>;
type M = BTreeMap<u64, V>;
const MAX_TIME: u64 = 253_402_300_799;
pub struct SignedInput<'a> {
    pub wire: &'a [u8],
    pub payload: &'a [u8],
    pub signer: &'a SuppliedTestRoot,
}
#[derive(Debug)]
pub struct CheckedFixtureChain {
    pub not_before: u64,
    pub expires: u64,
    pub leaf_digest: [u8; 32],
    pub delegatee: [u8; 32],
}
fn need(ok: bool, s: &'static str) -> R<()> {
    if ok { Ok(()) } else { Err(Reject::Invalid(s)) }
}
fn map(v: &V) -> R<&M> {
    Ok(codec::map(v)?)
}
fn get(m: &M, k: u64) -> R<&V> {
    Ok(codec::get(m, k)?)
}
fn uint(v: &V) -> R<u64> {
    Ok(codec::uint(v)?)
}
fn bytes(v: &V, lo: usize, hi: usize) -> R<&[u8]> {
    match v {
        V::Bytes(b) if (lo..=hi).contains(&b.len()) => Ok(b),
        _ => Err(Reject::Invalid("byte bounds")),
    }
}
fn text(v: &V) -> R<&str> {
    match v {
        V::Text(s) => Ok(s),
        _ => Err(Reject::Invalid("text required")),
    }
}
fn array(v: &V) -> R<&[V]> {
    match v {
        V::Array(a) => Ok(a),
        _ => Err(Reject::Invalid("array required")),
    }
}
fn fields(m: &M, required: &[u64], optional: &[u64]) -> R<()> {
    need(
        required.iter().all(|k| m.contains_key(k))
            && m.keys()
                .all(|k| required.contains(k) || optional.contains(k)),
        "closed fields",
    )
}
// Recognize ASCII A-label shape only. ACE semantics deliberately remain unsupported.
fn name(v: &V, unsupported: &mut bool) -> R<()> {
    let s = text(v)?;
    need(
        !s.is_empty() && s.len() <= 255 && s.is_ascii() && s == s.to_ascii_lowercase(),
        "canonical name shape",
    )?;
    for l in s.split('.') {
        need(
            !l.is_empty()
                && l.len() <= 63
                && l.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                && !l.starts_with('-')
                && !l.ends_with('-'),
            "canonical label shape",
        )?;
        *unsupported |= l.starts_with("xn--");
    }
    Ok(())
}
fn reference(v: &V) -> R<&M> {
    let m = map(v)?;
    fields(m, &[1, 2, 3, 4], &[])?;
    need((1..=14).contains(&uint(get(m, 1)?)?), "reference class")?;
    bytes(get(m, 2)?, 1, 64)?;
    if get(m, 3)? != &V::Null {
        bytes(get(m, 3)?, 1, 64)?;
    }
    if get(m, 4)? != &V::Null {
        bytes(get(m, 4)?, 32, 32)?;
    }
    Ok(m)
}
fn actor(v: &V, class: u64) -> R<&[u8]> {
    let m = reference(v)?;
    need(uint(get(m, 1)?)? == class, "actor class")?;
    let id = bytes(get(m, 2)?, 32, 32)?;
    need(bytes(get(m, 4)?, 32, 32)? == id, "operator actor binding")?;
    Ok(id)
}
fn target(v: &V) -> R<()> {
    let m = map(v)?;
    fields(m, &[1, 2, 3], &[])?;
    need((1..=18).contains(&uint(get(m, 1)?)?), "target class")?;
    bytes(get(m, 2)?, 1, 64)?;
    if get(m, 3)? != &V::Null {
        bytes(get(m, 3)?, 32, 32)?;
    }
    Ok(())
}
fn extensions(v: &V) -> R<()> {
    let m = map(v)?;
    need(m.len() <= 16, "extension count")?;
    for (id, v) in m {
        need((1000..=65535).contains(id), "extension id")?;
        let x = map(v)?;
        fields(x, &[1, 2, 3], &[])?;
        need(
            (1..=65535).contains(&uint(get(x, 1)?)?),
            "extension version",
        )?;
        need(
            get(x, 2)? == &V::Bool(false),
            "unknown critical or malformed extension",
        )?;
        bytes(get(x, 3)?, 0, 4096)?;
    }
    Ok(())
}
fn common(
    m: &M,
    kind: u64,
    signer: &SuppliedTestRoot,
    now: u64,
    unsupported: &mut bool,
) -> R<(u64, u64)> {
    need(
        uint(get(m, 1)?)? == kind && uint(get(m, 2)?)? == 1,
        "object type/version",
    )?;
    let generation = uint(get(m, 4)?)?;
    let sequence = uint(get(m, 5)?)?;
    need(generation > 0 && sequence > 0, "positive lineage")?;
    if let Some(v) = m.get(&8) {
        bytes(v, 32, 32)?;
        need(generation != 1 || sequence != 1, "genesis predecessor")?;
    }
    if generation != 1 || sequence != 1 {
        need(m.contains_key(&8), "update predecessor")?;
    }
    *unsupported |= generation != 1 || sequence != 1;
    if let Some(v) = m.get(&31) {
        extensions(v)?;
        *unsupported = true;
    }
    let issuer = reference(get(m, 3)?)?;
    need(
        bytes(get(issuer, 4)?, 32, 32)? == signer.operator
            && bytes(get(issuer, 2)?, 32, 32)? == signer.operator,
        "signer operator",
    )?;
    // Optional reference syntax does not remove signed NOR/delegation kid binding.
    need(
        bytes(get(issuer, 3)?, 1, 64)? == signer.kid,
        "issuer key binding",
    )?;
    need(
        signer.purpose == kind + 2
            && signer.lifecycle == 2
            && !signer.revoked
            && signer.generation > 0
            && signer.sequence > 0,
        "active signer purpose/lineage",
    )?;
    let a = uint(get(m, 6)?)?;
    let b = uint(get(m, 7)?)?;
    need(
        a < b && b <= MAX_TIME && a <= now && now <= b,
        "record validity",
    )?;
    need(
        signer.not_before < signer.expires
            && signer.expires <= MAX_TIME
            && signer.not_before <= now
            && now <= signer.expires,
        "signer validity",
    )?;
    Ok((a, b))
}
fn scope<'a>(v: &'a V, unsupported: &mut bool) -> R<&'a M> {
    let m = map(v)?;
    fields(m, &[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], &[])?;
    if get(m, 1)? != &V::Null {
        name(get(m, 1)?, unsupported)?;
    }
    for (k, lo, hi) in [(2, 32, 32), (3, 1, 64), (4, 32, 32), (5, 32, 32)] {
        if get(m, k)? != &V::Null {
            bytes(get(m, k)?, lo, hi)?;
        }
    }
    if get(m, 6)? != &V::Null {
        need((1..=32).contains(&text(get(m, 6)?)?.len()), "region bounds")?;
    }
    let ranges = array(get(m, 7)?)?;
    need(ranges.len() <= 32, "port count")?;
    let mut prior = None;
    for v in ranges {
        let p = array(v)?;
        need(p.len() == 2, "port pair")?;
        let a = uint(&p[0])?;
        let b = uint(&p[1])?;
        need(
            a >= 1 && a <= b && b <= 65535 && prior.is_none_or(|old| a > old + 1),
            "ordered disjoint ports",
        )?;
        prior = Some(b);
    }
    for (k, max) in [(8, 16), (9, 32)] {
        let a = array(get(m, k)?)?;
        need(!a.is_empty() && a.len() <= max, "scope list bounds")?;
        let mut prior = None;
        for v in a {
            let n = uint(v)?;
            need(prior.is_none_or(|p| n > p), "sorted unique scope list")?;
            prior = Some(n);
        }
    }
    need(
        matches!(get(m, 10)?, V::Bool(_)) && uint(get(m, 11)?)? <= 8,
        "scope depth/flag",
    )?;
    need(codec::encode(v).len() <= 2048, "scope encoding bound")?;
    Ok(m)
}
fn narrow(parent: &M, child: &M) -> R<()> {
    for k in 1..=6 {
        need(get(parent, k)? == get(child, k)?, "exact scope dimension")?;
    }
    for item in array(get(child, 7)?)? {
        let p = array(item)?;
        let a = uint(&p[0])?;
        let b = uint(&p[1])?;
        let covered = array(get(parent, 7)?)?.iter().any(|v| {
            let V::Array(p) = v else { return false };
            matches!((&p[0],&p[1]),(V::Uint(x),V::Uint(y)) if *x<=a&&b<=*y)
        });
        need(covered, "port widening")?;
    }
    for k in [8, 9] {
        need(
            array(get(child, k)?)?
                .iter()
                .all(|v| array(get(parent, k).unwrap()).unwrap().contains(v)),
            "protocol/action widening",
        )?;
    }
    need(
        get(parent, 10)? != &V::Bool(false) || get(child, 10)? == &V::Bool(false),
        "subdelegation widening",
    )?;
    need(
        uint(get(child, 11)?)? <= uint(get(parent, 11)?)?,
        "depth widening",
    )
}
pub fn verify(chain: &[SignedInput<'_>], request: &[u8], now: u64) -> R<CheckedFixtureChain> {
    need(
        chain.len() == 2 && now <= MAX_TIME && request.len() <= 2048,
        "bounded two-object context",
    )?;
    // Authenticate both exact signed byte strings before any semantic classification.
    for i in chain {
        signature::verify_exact(i.wire, i.payload, &i.signer.kid, &i.signer.key)?;
        need(i.payload.len() <= 32768, "record bound")?;
    }
    semantics(chain, request, now)
}
// Private unsigned semantic stage; only verify() authenticates inputs and exposes evidence.
fn semantics(chain: &[SignedInput<'_>], request: &[u8], now: u64) -> R<CheckedFixtureChain> {
    let root = codec::decode_value(chain[0].payload)?;
    let grant = codec::decode_value(chain[1].payload)?;
    let req = codec::decode_value(request)?;
    let r = map(&root)?;
    let d = map(&grant)?;
    let mut unsupported = false;
    fields(r, &[1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 36, 37], &[8, 31, 35])?;
    fields(d, &[1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 36, 37], &[8, 31, 35])?;
    let rw = common(r, 3, chain[0].signer, now, &mut unsupported)?;
    let dw = common(d, 4, chain[1].signer, now, &mut unsupported)?;
    let owner = actor(get(r, 33)?, 7)?;
    actor(get(r, 3)?, 7)?;
    need(owner == chain[0].signer.operator, "owner/issuer binding")?;
    name(get(r, 32)?, &mut unsupported)?;
    let service = bytes(get(r, 34)?, 32, 32)?;
    if uint(get(r, 4)?)? == 1 && uint(get(r, 5)?)? == 1 {
        let s = text(get(r, 32)?)?;
        let mut hash = Sha256::new();
        hash.update(b"NBSR-FEDERATION-SERVICE-ID-v1\0");
        hash.update(owner);
        hash.update((s.len() as u16).to_be_bytes());
        hash.update(s.as_bytes());
        need(hash.finalize().as_slice() == service, "genesis service ID")?;
    }
    if let Some(v) = r.get(&35)
        && v != &V::Null
    {
        bytes(v, 32, 32)?;
    }
    need(uint(get(r, 36)?)? <= 3, "ownership transfer state")?;
    unsupported |= uint(get(r, 36)?)? != 0;
    for v in [get(r, 37)?, get(d, 37)?] {
        if v != &V::Null {
            target(v)?;
            return Err(Reject::Invalid("revoked record"));
        }
    }
    let delegator = reference(get(d, 32)?)?;
    let class = uint(get(delegator, 1)?)?;
    need(class == 7 || class == 8, "delegator class")?;
    let actor_id = actor(get(d, 32)?, class)?;
    need(get(d, 3)? == get(d, 32)?, "issuer/delegator exact binding")?;
    let delegatee = actor(get(d, 33)?, 8)?;
    need(delegatee != actor_id && delegatee != owner, "actor loop")?;
    if let Some(v) = d.get(&35) {
        bytes(v, 32, 32)?;
    }
    if class == 7 {
        if uint(get(d, 4)?)? == 1 && uint(get(d, 5)?)? == 1 {
            need(!d.contains_key(&35), "direct genesis parent digest")?;
        }
        need(actor_id == owner, "direct owner binding")?;
    } else {
        need(d.contains_key(&35), "child parent required")?;
        unsupported = true;
    }
    if get(d, 36)? != &V::Null {
        bytes(get(d, 36)?, 32, 32)?;
    }
    let s = scope(get(d, 34)?, &mut unsupported)?;
    let q = scope(&req, &mut unsupported)?;
    need(
        get(s, 1)? == get(r, 32)? && get(s, 2)? == get(r, 34)?,
        "ownership scope binding",
    )?;
    need(
        rw.0 <= dw.0 && dw.1 <= rw.1,
        "delegation validity containment",
    )?;
    narrow(s, q)?;
    if unsupported {
        return Err(Reject::Unsupported("recognized outside genesis LDH slice"));
    }
    Ok(CheckedFixtureChain {
        not_before: rw
            .0
            .max(dw.0)
            .max(chain[0].signer.not_before)
            .max(chain[1].signer.not_before),
        expires: rw
            .1
            .min(dw.1)
            .min(chain[0].signer.expires)
            .min(chain[1].signer.expires),
        leaf_digest: Sha256::digest(chain[1].payload).into(),
        delegatee: delegatee
            .try_into()
            .map_err(|_| Reject::Invalid("delegatee length"))?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value as J;
    fn hex(s: &str) -> Vec<u8> {
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
            .collect()
    }
    fn edit(v: &mut V) -> &mut M {
        let V::Map(m) = v else { panic!("fixture map") };
        m
    }
    fn fixture() -> J {
        serde_json::from_str(include_str!("../fixtures/connector-genesis-evidence.json")).unwrap()
    }
    fn signer() -> SuppliedTestRoot {
        SuppliedTestRoot {
            operator: [b'A'; 32],
            kid: b"key".to_vec(),
            key: hex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
                .try_into()
                .unwrap(),
            purpose: 5,
            lifecycle: 2,
            generation: 1,
            sequence: 1,
            not_before: 800,
            expires: 2100,
            revoked: false,
        }
    }
    // Deliberately unsigned parser probes; never report these as signed conformance.
    fn semantic_mutation(change: impl FnOnce(&mut V, &mut V, &mut V)) -> R<CheckedFixtureChain> {
        let f = fixture();
        let c = &f["cases"][0];
        let mut r = codec::decode_value(&hex(c["chain"][0]["payload"].as_str().unwrap())).unwrap();
        let mut d = codec::decode_value(&hex(c["chain"][1]["payload"].as_str().unwrap())).unwrap();
        let mut q = codec::decode_value(&hex(c["request_scope"].as_str().unwrap())).unwrap();
        change(&mut r, &mut d, &mut q);
        let a = signer();
        let mut b = a.clone();
        b.purpose = 6;
        let rp = codec::encode(&r);
        let dp = codec::encode(&d);
        semantics(
            &[
                SignedInput {
                    wire: &[],
                    payload: &rp,
                    signer: &a,
                },
                SignedInput {
                    wire: &[],
                    payload: &dp,
                    signer: &b,
                },
            ],
            &codec::encode(&q),
            1000,
        )
    }
    #[test]
    fn malformed_or_unknown_fields_are_invalid_not_unsupported() {
        for which in 0..6 {
            let result = semantic_mutation(|r, d, q| match which {
                0 => {
                    edit(r).remove(&32);
                }
                1 => {
                    edit(r).insert(999, V::Null);
                }
                2 => {
                    edit(d).insert(35, V::Bool(false));
                }
                3 => {
                    edit(q).insert(8, V::Array(vec![V::Uint(6), V::Uint(6)]));
                }
                4 => {
                    edit(r).insert(31, V::Bool(false));
                }
                _ => {
                    edit(edit(r).get_mut(&3).unwrap()).insert(3, V::Null);
                }
            });
            assert!(
                matches!(result, Err(Reject::Invalid(_))),
                "{which}: {result:?}"
            );
        }
    }
    #[test]
    fn recognized_ace_update_extension_and_child_are_unsupported() {
        for which in 0..5 {
            let result = semantic_mutation(|r, d, q| match which {
                0 => {
                    let n = "xn--bcher-kva.example";
                    let mut h = Sha256::new();
                    h.update(b"NBSR-FEDERATION-SERVICE-ID-v1\0");
                    h.update([b'A'; 32]);
                    h.update((n.len() as u16).to_be_bytes());
                    h.update(n.as_bytes());
                    let id = V::Bytes(h.finalize().to_vec());
                    edit(r).insert(32, V::Text(n.into()));
                    edit(r).insert(34, id.clone());
                    let s = edit(edit(d).get_mut(&34).unwrap());
                    s.insert(1, V::Text(n.into()));
                    s.insert(2, id.clone());
                    edit(q).insert(1, V::Text(n.into()));
                    edit(q).insert(2, id);
                }
                1 => {
                    edit(r).insert(5, V::Uint(2));
                    edit(r).insert(8, V::Bytes(vec![b'P'; 32]));
                }
                2 => {
                    let extension = V::Map(BTreeMap::from([
                        (1, V::Uint(1)),
                        (2, V::Bool(false)),
                        (3, V::Bytes(vec![])),
                    ]));
                    edit(r).insert(31, V::Map(BTreeMap::from([(1000, extension)])));
                }
                3 => {
                    for k in [3, 32] {
                        edit(edit(d).get_mut(&k).unwrap()).insert(1, V::Uint(8));
                    }
                    edit(d).insert(35, V::Bytes(vec![b'P'; 32]));
                }
                _ => {
                    edit(d).insert(5, V::Uint(2));
                    edit(d).insert(8, V::Bytes(vec![b'P'; 32]));
                    edit(d).insert(35, V::Bytes(vec![b'Q'; 32]));
                }
            });
            assert!(
                matches!(result, Err(Reject::Unsupported(_))),
                "{which}: {result:?}"
            );
        }
    }
    #[test]
    fn signed_input_checks_key_purpose_operator_lifecycle_and_time() {
        let f = fixture();
        let c = &f["cases"][0];
        let wires: Vec<_> = (0..2)
            .map(|i| hex(c["chain"][i]["wire"].as_str().unwrap()))
            .collect();
        let payloads: Vec<_> = (0..2)
            .map(|i| hex(c["chain"][i]["payload"].as_str().unwrap()))
            .collect();
        let q = hex(c["request_scope"].as_str().unwrap());
        for which in 0..8 {
            let mut a = signer();
            let mut b = a.clone();
            b.purpose = 6;
            match which {
                0 => a.purpose = 6,
                1 => b.operator = [b'B'; 32],
                2 => a.key[0] ^= 1,
                3 => b.kid.push(0),
                4 => a.lifecycle = 3,
                5 => b.revoked = true,
                6 => a.not_before = 1001,
                _ => b.expires = 999,
            }
            let result = verify(
                &[
                    SignedInput {
                        wire: &wires[0],
                        payload: &payloads[0],
                        signer: &a,
                    },
                    SignedInput {
                        wire: &wires[1],
                        payload: &payloads[1],
                        signer: &b,
                    },
                ],
                &q,
                1000,
            );
            assert!(
                matches!(result, Err(Reject::Invalid(_))),
                "{which}: {result:?}"
            );
        }
        let a = signer();
        let mut b = a.clone();
        b.purpose = 6;
        b.expires = 1500;
        let result = verify(
            &[
                SignedInput {
                    wire: &wires[0],
                    payload: &payloads[0],
                    signer: &a,
                },
                SignedInput {
                    wire: &wires[1],
                    payload: &payloads[1],
                    signer: &b,
                },
            ],
            &q,
            1000,
        )
        .unwrap();
        assert_eq!(result.not_before, 900);
        assert_eq!(result.expires, 1500);
        let mut bad = wires[1].clone();
        *bad.last_mut().unwrap() ^= 1;
        assert!(matches!(
            verify(
                &[
                    SignedInput {
                        wire: &wires[0],
                        payload: &payloads[0],
                        signer: &a
                    },
                    SignedInput {
                        wire: &bad,
                        payload: &payloads[1],
                        signer: &b
                    }
                ],
                &q,
                1000
            ),
            Err(Reject::Invalid(_))
        ));
    }
}
