//! Test-only request-body/evidence consistency, not session admission or READY.
use crate::{
    codec::{self, Value as V},
    genesis::{self, Reject, SignedInput},
    kar,
};
use sha2::{Digest, Sha256};

// Separately supplied fixture trust. No constructor accepts signed evidence.
// Matches Python signer_identity's ten fields and 1..=64 inventory bound.
pub struct SignerInventory {
    identities: Vec<kar::SuppliedTestRoot>,
}
fn valid_identity(s: &kar::SuppliedTestRoot) -> bool {
    (1..=64).contains(&s.kid.len())
        && (1..=16).contains(&s.purpose)
        && (1..=5).contains(&s.lifecycle)
        && s.generation > 0
        && s.sequence > 0
        && s.not_before <= s.expires
        && s.expires <= 253_402_300_799
}
fn same_identity(a: &kar::SuppliedTestRoot, b: &kar::SuppliedTestRoot) -> bool {
    a.kid == b.kid
        && a.key == b.key
        && a.operator == b.operator
        && a.purpose == b.purpose
        && a.lifecycle == b.lifecycle
        && a.generation == b.generation
        && a.sequence == b.sequence
        && a.not_before == b.not_before
        && a.expires == b.expires
        && a.revoked == b.revoked
}
impl SignerInventory {
    pub fn supplied(identities: &[kar::SuppliedTestRoot]) -> Result<Self, Reject> {
        need(
            (1..=64).contains(&identities.len()),
            "fixture signer inventory bounds",
        )?;
        need(
            identities.iter().all(valid_identity),
            "invalid fixture signer identity",
        )?;
        Ok(Self {
            identities: identities.to_vec(),
        })
    }
    fn check(&self, signer: &kar::SuppliedTestRoot) -> Result<(), Reject> {
        need(valid_identity(signer), "invalid fixture signer identity")?;
        need(
            self.identities
                .iter()
                .any(|allowed| same_identity(allowed, signer)),
            "signer absent from exact fixture inventory",
        )
    }
}

pub struct Context<'a> {
    pub policy: &'a [u8],
    pub scope: &'a [u8],
    pub inventory: &'a V,
    pub signers: &'a SignerInventory,
    pub peer: &'a [u8; 32],
    pub key: SignedInput<'a>,
    pub chain: &'a [SignedInput<'a>],
    pub now: u64,
}
#[derive(Debug)]
pub struct CheckedFixtureBinding {
    pub request_digest: [u8; 32],
    pub evidence_expires: u64,
}
fn need(ok: bool, why: &'static str) -> Result<(), Reject> {
    if ok {
        Ok(())
    } else {
        Err(Reject::Invalid(why))
    }
}
pub fn verify(raw: &[u8], context: &Context<'_>) -> Result<CheckedFixtureBinding, Reject> {
    need(
        raw.len() <= 16384 && context.policy.len() <= 16384,
        "request bounds",
    )?;
    let body = codec::decode_value(raw)?;
    let policy = codec::decode_value(context.policy)?;
    codec::validate_body(codec::REQUEST, &body)?;
    codec::validate_body(codec::REQUEST, &policy)?;
    let q = codec::map(&body)?;
    let p = codec::map(&policy)?;
    for k in [2, 3, 4, 5, 6, 7, 8, 12] {
        need(codec::get(q, k)? == codec::get(p, k)?, "policy pin")?;
    }
    let scope_value = codec::decode_value(context.scope)?;
    let scope = codec::map(&scope_value)?;
    for (s, k) in [(2, 3), (4, 4), (5, 5)] {
        need(
            codec::get(scope, s)? == codec::get(p, k)?,
            "scope policy binding",
        )?;
    }
    need(
        codec::get(scope, 9)? == &V::Array(vec![V::Uint(codec::REQUEST)])
            && codec::get(scope, 10)? == &V::Bool(false)
            && codec::get(scope, 11)? == &V::Uint(0),
        "registration-only scope",
    )?;
    need(
        Sha256::digest(context.peer).as_slice() == codec::bytes(codec::get(q, 8)?, 32, false)?,
        "actual peer",
    )?;
    need(context.chain.len() == 2, "bounded two-object context")?;
    context.signers.check(context.key.signer)?;
    for record in context.chain {
        context.signers.check(record.signer)?;
    }
    let expected = kar::ExpectedKey {
        operator: codec::bytes(codec::get(q, 4)?, 32, false)?
            .try_into()
            .map_err(|_| Reject::Invalid("operator length"))?,
        kid: match codec::get(q, 7)? {
            V::Bytes(b) => b.clone(),
            _ => return Err(Reject::Invalid("key id")),
        },
        key: *context.peer,
        purpose: 14,
        terminal_ids: vec![], // Explicit supplied fixture context, not current revocation evidence.
    };
    let checked_key = kar::verify_genesis(
        context.key.wire,
        context.key.payload,
        context.key.signer,
        &expected,
        context.now,
    )?;
    let checked_chain = genesis::verify(context.chain, context.scope, context.now)?;
    need(
        checked_chain.delegatee == expected.operator,
        "verified delegatee",
    )?;
    let mut records = vec![V::Array(vec![
        V::Uint(2),
        V::Bytes(Sha256::digest(context.key.payload).to_vec()),
    ])];
    for (i, record) in context.chain.iter().enumerate() {
        records.push(V::Array(vec![
            V::Uint(i as u64 + 3),
            V::Bytes(Sha256::digest(record.payload).to_vec()),
        ]));
    }
    records.sort_by_key(codec::encode);
    let records = V::Array(records);
    need(&records == context.inventory, "configured inventory")?;
    need(&records == codec::get(q, 10)?, "request inventory")?;
    need(
        Sha256::digest(context.key.payload).as_slice()
            == codec::bytes(codec::get(q, 9)?, 32, false)?,
        "request KAR digest",
    )?;
    Ok(CheckedFixtureBinding {
        request_digest: Sha256::digest(raw).into(),
        evidence_expires: checked_chain
            .expires
            .min(checked_key.valid_window(context.now, context.now)?),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use kar::SuppliedTestRoot;
    use serde_json::Value as J;
    fn hex(s: &str) -> Vec<u8> {
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
            .collect()
    }
    fn digest(b: &[u8]) -> V {
        V::Bytes(Sha256::digest(b).to_vec())
    }
    struct Fixture {
        wires: Vec<Vec<u8>>,
        payloads: Vec<Vec<u8>>,
        roots: Vec<SuppliedTestRoot>,
        peer: [u8; 32],
        scope: Vec<u8>,
        body: V,
        policy: Vec<u8>,
        inventory: V,
        signers: SignerInventory,
    }
    impl Fixture {
        fn new() -> Self {
            let k: J = serde_json::from_str(include_str!(
                "../fixtures/connector-kar-transport-positive.json"
            ))
            .unwrap();
            let g: J =
                serde_json::from_str(include_str!("../fixtures/connector-genesis-evidence.json"))
                    .unwrap();
            let c = &g["cases"][0];
            let wires = vec![
                hex(k["wire"].as_str().unwrap()),
                hex(c["chain"][0]["wire"].as_str().unwrap()),
                hex(c["chain"][1]["wire"].as_str().unwrap()),
            ];
            let payloads = vec![
                hex(k["payload"].as_str().unwrap()),
                hex(c["chain"][0]["payload"].as_str().unwrap()),
                hex(c["chain"][1]["payload"].as_str().unwrap()),
            ];
            let peer: [u8; 32] = hex(k["public_key"].as_str().unwrap()).try_into().unwrap();
            let roots = [(b'C', 1), (b'A', 5), (b'A', 6)]
                .into_iter()
                .map(|(op, purpose)| SuppliedTestRoot {
                    operator: [op; 32],
                    kid: b"key".to_vec(),
                    key: peer,
                    purpose,
                    lifecycle: 2,
                    generation: 1,
                    sequence: 1,
                    not_before: 800,
                    expires: 2100,
                    revoked: false,
                })
                .collect();
            let scope = hex(c["request_scope"].as_str().unwrap());
            let scope_value = codec::decode_value(&scope).unwrap();
            let sm = codec::map(&scope_value).unwrap();
            let inventory = V::Array(
                payloads
                    .iter()
                    .enumerate()
                    .map(|(i, p)| V::Array(vec![V::Uint(i as u64 + 2), digest(p)]))
                    .collect(),
            );
            let body = V::Map(
                [
                    (0, V::Uint(1)),
                    (1, V::Text("register".into())),
                    (2, V::Text("connector-a".into())),
                    (3, sm[&2].clone()),
                    (4, sm[&4].clone()),
                    (5, sm[&5].clone()),
                    (6, V::Text("gateway-a".into())),
                    (7, V::Bytes(b"transport-key".to_vec())),
                    (8, digest(&peer)),
                    (9, digest(&payloads[0])),
                    (10, inventory.clone()),
                    (11, digest(&codec::encode(&inventory))),
                    (12, V::Bytes(vec![b'P'; 32])),
                    (13, V::Uint(60)),
                    (14, V::Uint(1000)),
                    (15, V::Null),
                ]
                .into_iter()
                .collect(),
            );
            let policy = codec::encode(&body);
            // Independent pinned public test configuration, not read from evidence roots.
            let pinned_key: [u8; 32] =
                hex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
                    .try_into()
                    .unwrap();
            let allowed: Vec<_> = [(b'C', 1), (b'A', 5), (b'A', 6)]
                .into_iter()
                .map(|(op, purpose)| SuppliedTestRoot {
                    operator: [op; 32],
                    kid: b"key".to_vec(),
                    key: pinned_key,
                    purpose,
                    lifecycle: 2,
                    generation: 1,
                    sequence: 1,
                    not_before: 800,
                    expires: 2100,
                    revoked: false,
                })
                .collect();
            let signers = SignerInventory::supplied(&allowed).unwrap();
            Self {
                wires,
                payloads,
                roots,
                peer,
                scope,
                body,
                policy,
                inventory,
                signers,
            }
        }
        fn check(&self) -> Result<CheckedFixtureBinding, Reject> {
            let inputs: Vec<_> = (0..3)
                .map(|i| SignedInput {
                    wire: &self.wires[i],
                    payload: &self.payloads[i],
                    signer: &self.roots[i],
                })
                .collect();
            verify(
                &codec::encode(&self.body),
                &Context {
                    policy: &self.policy,
                    scope: &self.scope,
                    inventory: &self.inventory,
                    signers: &self.signers,
                    peer: &self.peer,
                    key: SignedInput {
                        wire: &self.wires[0],
                        payload: &self.payloads[0],
                        signer: &self.roots[0],
                    },
                    chain: &inputs[1..],
                    now: 1000,
                },
            )
        }
        fn set(&mut self, k: u64, v: V) {
            if let V::Map(m) = &mut self.body {
                m.insert(k, v);
            }
        }
        fn pin_body(&mut self) {
            self.policy = codec::encode(&self.body);
        }
    }
    #[test]
    fn exact_body_binds_existing_signed_evidence_without_admission_claim() {
        let f = Fixture::new();
        let checked = f.check().unwrap();
        assert_eq!(
            checked.request_digest,
            <[u8; 32]>::from(Sha256::digest(codec::encode(&f.body)))
        );
        assert_eq!(checked.evidence_expires, 1800); // NOT offline freshness/admission1700.
    }
    #[test]
    fn mismatched_policy_peer_inventory_and_dependencies_fail_closed() {
        for field in [2, 3, 4, 5, 6, 7, 8, 12] {
            let mut f = Fixture::new();
            let value = match field {
                2 | 6 => V::Text("other".into()),
                7 => V::Bytes(b"other".to_vec()),
                _ => V::Bytes(vec![b'X'; 32]),
            };
            f.set(field, value);
            assert!(
                matches!(f.check(), Err(Reject::Invalid(_))),
                "field {field}"
            );
        }
        let mut f = Fixture::new();
        f.peer = [b'X'; 32];
        assert!(matches!(f.check(), Err(Reject::Invalid(_))));
        let mut f = Fixture::new();
        f.inventory = V::Array(vec![]);
        assert!(matches!(f.check(), Err(Reject::Invalid(_))));
        for field in [9, 11] {
            let mut f = Fixture::new();
            f.set(field, V::Bytes(vec![b'X'; 32]));
            assert!(matches!(f.check(), Err(Reject::Invalid(_))));
        }
        let mut f = Fixture::new();
        f.set(7, V::Bytes(b"different-key".to_vec()));
        f.pin_body();
        assert!(matches!(f.check(), Err(Reject::Invalid(_))));
    }
    #[test]
    fn replacing_valid_evidence_and_request_cannot_replace_configured_inventory() {
        let mut f = Fixture::new();
        let g: J =
            serde_json::from_str(include_str!("../fixtures/connector-genesis-evidence.json"))
                .unwrap();
        let c = g["cases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["id"] == "narrow_requested_port")
            .unwrap();
        f.wires[2] = hex(c["chain"][1]["wire"].as_str().unwrap());
        f.payloads[2] = hex(c["chain"][1]["payload"].as_str().unwrap());
        let refs = V::Array(
            f.payloads
                .iter()
                .enumerate()
                .map(|(i, p)| V::Array(vec![V::Uint(i as u64 + 2), digest(p)]))
                .collect(),
        );
        f.set(10, refs.clone());
        f.set(11, digest(&codec::encode(&refs)));
        f.pin_body();
        assert!(matches!(
            f.check(),
            Err(Reject::Invalid("configured inventory"))
        ));
        f.inventory = refs;
        assert!(f.check().is_ok()); // Explicit updated fixture inventory, not live trust.
    }
    #[test]
    fn missing_extra_dependencies_and_scope_substitution_reject() {
        for extra in [false, true] {
            let mut f = Fixture::new();
            let mut refs = if let V::Array(a) = &f.inventory {
                a.clone()
            } else {
                unreachable!()
            };
            if extra {
                refs.push(V::Array(vec![V::Uint(5), V::Bytes(vec![b'X'; 32])]));
            } else {
                refs.pop();
            }
            let refs = V::Array(refs);
            f.set(10, refs.clone());
            f.set(11, digest(&codec::encode(&refs)));
            f.pin_body();
            assert!(matches!(f.check(), Err(Reject::Invalid(_))));
        }
        let mut f = Fixture::new();
        let mut scope = codec::decode_value(&f.scope).unwrap();
        if let V::Map(m) = &mut scope {
            m.insert(2, V::Bytes(vec![b'X'; 32]));
        }
        f.scope = codec::encode(&scope);
        assert!(matches!(f.check(), Err(Reject::Invalid(_))));
    }
    #[test]
    fn each_signer_identity_field_is_independently_pinned() {
        for signer in 0..3 {
            for field in 0..10 {
                let mut f = Fixture::new();
                let s = &mut f.roots[signer];
                match field {
                    0 => s.kid = b"other".to_vec(),
                    1 => s.key[0] ^= 1,
                    2 => s.operator[0] ^= 1,
                    3 => s.purpose = 2,
                    4 => s.lifecycle = 3,
                    5 => s.generation += 1,
                    6 => s.sequence += 1,
                    7 => s.not_before += 1,
                    8 => s.expires -= 1,
                    _ => s.revoked = true,
                }
                assert!(
                    matches!(
                        f.check(),
                        Err(Reject::Invalid(
                            "signer absent from exact fixture inventory"
                        ))
                    ),
                    "signer {signer} field {field}"
                );
            }
        }
    }
    #[test]
    fn evidence_cannot_self_select_trust_or_mutate_supplied_snapshot() {
        let mut f = Fixture::new();
        // Expiry extension preserves signatures: metadata is not signed evidence.
        f.roots[1].expires = 2200;
        assert!(matches!(
            f.check(),
            Err(Reject::Invalid(
                "signer absent from exact fixture inventory"
            ))
        ));
        // Explicitly changing LOCAL test inventory is a separate action, not auto-trust.
        f.signers = SignerInventory::supplied(&f.roots).unwrap();
        assert!(f.check().is_ok());
        f.roots[1].expires = 2300;
        assert!(matches!(
            f.check(),
            Err(Reject::Invalid(
                "signer absent from exact fixture inventory"
            ))
        ));
    }
    #[test]
    fn signer_inventory_bounds_identity_validation_and_set_semantics() {
        let f = Fixture::new();
        assert!(SignerInventory::supplied(&[]).is_err());
        assert!(SignerInventory::supplied(&vec![f.roots[0].clone(); 65]).is_err());
        assert!(SignerInventory::supplied(&vec![f.roots[0].clone(); 64]).is_ok());
        for field in 0..8 {
            let mut s = f.roots[0].clone();
            match field {
                0 => s.kid.clear(),
                1 => s.kid = vec![1; 65],
                2 => s.purpose = 17,
                3 => s.lifecycle = 0,
                4 => s.generation = 0,
                5 => s.sequence = 0,
                6 => s.not_before = s.expires + 1,
                _ => s.expires = 253_402_300_800,
            }
            assert!(matches!(
                SignerInventory::supplied(&[s]),
                Err(Reject::Invalid(_))
            ));
        }
        let mut f = Fixture::new();
        let mut allowed = f.roots.clone();
        allowed.reverse();
        allowed.push(allowed[0].clone());
        f.signers = SignerInventory::supplied(&allowed).unwrap();
        assert!(f.check().is_ok());
        let mut extra = f.roots[0].clone();
        extra.operator = [0; 32];
        extra.not_before = extra.expires;
        allowed.push(extra);
        f.signers = SignerInventory::supplied(&allowed).unwrap();
        assert!(f.check().is_ok());
        // Python permits unused valid inventory members, duplicates and equal validity endpoints.
    }
}
