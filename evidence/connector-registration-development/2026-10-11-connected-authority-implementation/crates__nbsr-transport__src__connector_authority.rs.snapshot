//! Explicit supplied-test-trust normal negative enforcement. Never runtime authority.
#![cfg(test)]
use crate::{
    cleanup::CleanupTicket,
    codec::{self, Result, Value as V, get, map, uint},
    owner::{Binding, Gateway, Owner},
    signature,
};
use serde_json::Value as J;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
};

const PROFILE: &str = "nbsr-federation-revocation-inclusion-dev-v1";
const GROUP: &str = "normal-revocation";
fn hash(raw: &[u8]) -> Vec<u8> {
    Sha256::digest(raw).to_vec()
}
fn h(v: &V) -> V {
    V::Bytes(hash(&codec::encode(v)))
}
fn obj(fields: Vec<(u64, V)>) -> V {
    V::Map(fields.into_iter().collect())
}
fn b(v: &V) -> Result<&[u8]> {
    if let V::Bytes(x) = v {
        Ok(x)
    } else {
        Err("bytes required")
    }
}
fn a(v: &V) -> Result<&[V]> {
    if let V::Array(x) = v {
        Ok(x)
    } else {
        Err("array required")
    }
}
fn f(v: &V, k: u64) -> Result<&V> {
    get(map(v)?, k)
}
fn n(v: &V, k: u64) -> Result<u64> {
    uint(f(v, k)?)
}
fn text(s: &str) -> V {
    V::Text(s.into())
}
fn check(ok: bool) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err("local governed evidence rejected")
    }
}
fn exact(v: &V, keys: &[u64]) -> Result<()> {
    check(map(v)?.keys().copied().collect::<Vec<_>>() == keys)
}
fn unhex(s: &str) -> Result<Vec<u8>> {
    check(s.len().is_multiple_of(2))?;
    s.as_bytes()
        .chunks(2)
        .map(|p| {
            u8::from_str_radix(std::str::from_utf8(p).map_err(|_| "hex")?, 16).map_err(|_| "hex")
        })
        .collect()
}
fn jb(j: &J, k: &str) -> Result<Vec<u8>> {
    unhex(j[k].as_str().ok_or("missing hex")?)
}
fn jv(j: &J, k: &str) -> Result<V> {
    codec::decode_value(&jb(j, k)?)
}
fn ju(j: &J, k: &str) -> Result<u64> {
    j[k].as_u64().ok_or("missing uint")
}
fn active(j: &J, t: TimeWindow, purpose: u64) -> Result<()> {
    check(
        ju(j, "purpose")? == purpose
            && j["active"] == true
            && j["revoked"] == false
            && ju(j, "not_before")? <= t.earliest
            && t.latest <= ju(j, "expires")?,
    )
}
fn key_reference(j: &J, class: u64, purpose: u64, time: TimeWindow) -> Result<V> {
    active(j, time, purpose)?;
    let id = jb(j, "id")?;
    let kid = jb(j, "kid")?;
    check(id.len() == 32 && (1..=64).contains(&kid.len()) && jb(j, "key")?.len() == 32)?;
    Ok(obj(vec![
        (1, V::Uint(class)),
        (2, V::Bytes(id.clone())),
        (3, V::Bytes(kid)),
        (4, V::Bytes(id)),
    ]))
}
fn signed(wire: &V, key: &J, t: TimeWindow, purpose: u64) -> Result<V> {
    active(key, t, purpose)?;
    let raw = b(wire)?;
    check(raw.first() == Some(&0xd2))?;
    let outer = codec::decode_value(&raw[1..])?;
    let fields = a(&outer)?;
    check(fields.len() == 4)?;
    let payload = b(&fields[2])?;
    signature::verify_exact(
        raw,
        payload,
        &jb(key, "kid")?,
        &jb(key, "key")?.try_into().map_err(|_| "key size")?,
    )?;
    codec::decode_value(payload)
}
#[derive(Clone, Copy)]
pub struct TimeWindow {
    pub earliest: u64,
    pub latest: u64,
}
pub struct VerifiedOwnerEvent {
    provider: Arc<()>,
    revision: u64,
    owner: Owner,
    context: Vec<u8>,
    record: Vec<u8>,
    event: Vec<u8>,
    checkpoint: V,
    effect: u64,
    expires: u64,
}
pub enum Applied {
    Denied,
    Cleanup(Box<CleanupTicket>),
    Idempotent,
}
pub struct LocalAuthorityProvider {
    trust: J,
    policy: V,
    bundle: V,
    anchor: V,
    binding: Binding,
    identity: Arc<()>,
    context: Vec<u8>,
    revision: u64,
    last_time: u64,
    clock_failed: bool,
    record: Option<Vec<u8>>,
    events: BTreeMap<Vec<u8>, Vec<u8>>,
}
impl LocalAuthorityProvider {
    pub fn from_supplied_test_trust(
        raw: &[u8],
        expected: [u8; 32],
        binding: Binding,
        time: TimeWindow,
    ) -> Result<Self> {
        check(raw.len() <= 262144 && hash(raw) == expected)?;
        let trust: J = serde_json::from_slice(raw).map_err(|_| "test trust JSON")?;
        check(trust["label"] == "SuppliedTestTrust" && trust["profile"] == PROFILE)?;
        let bundle = jv(&trust, "bundle")?;
        let policy = jv(&trust, "policy")?;
        let anchor = jv(&trust, "anchor")?;
        check(hash(&jb(&trust, "bundle")?) == jb(&trust, "bundle_digest")?)?;
        exact(
            &bundle,
            &[1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41],
        )?;
        check(
            n(&bundle, 1)? == 5
                && n(&bundle, 2)? == 1
                && n(&bundle, 4)? == 1
                && n(&bundle, 5)? == 1,
        )?;
        check(f(&bundle, 32)? == &jv(&trust, "scope")? && f(&bundle, 41)? == f(&policy, 2)?)?;
        check(f(&policy, 3)? == &text("normal-revocation-v1") && n(&policy, 1)? == 1)?;
        exact(&policy, &[1, 2, 3, 4, 5, 6, 7, 9])?;
        check(
            f(&policy, 4)? == &V::Bool(true)
                && f(&policy, 6)? == &V::Array(vec![V::Uint(13)])
                && f(&policy, 7)? == &V::Array(vec![V::Uint(16407)])
                && f(&policy, 9)? == &V::Array(vec![text("deny")]),
        )?;
        let mut pd = map(&policy)?.clone();
        pd.insert(2, V::Null);
        check(f(&policy, 2)? == &h(&V::Map(pd)))?;
        let signers = trust["signers"].as_array().ok_or("missing roster")?;
        check(signers.len() == 5)?;
        let mut ids = BTreeSet::new();
        let mut orgs = BTreeSet::new();
        let mut controls = BTreeSet::new();
        let mut refs = Vec::new();
        let mut public_keys = BTreeSet::new();
        for signer in signers {
            active(signer, time, 12)?;
            check(ju(signer, "class")? == 4)?;
            key_reference(signer, 4, 12, time)?;
            check(
                public_keys.insert(jb(signer, "key")?)
                    && (1..=64).contains(&jb(signer, "organization")?.len()),
            )?;
            check(
                ids.insert(jb(signer, "id")?)
                    && orgs.insert(jb(signer, "organization")?)
                    && controls.insert(
                        signer["control"]
                            .as_str()
                            .filter(|s| !s.is_empty())
                            .ok_or("control")?
                            .to_owned(),
                    ),
            )?;
            let id = V::Bytes(jb(signer, "id")?);
            refs.push(obj(vec![
                (1, V::Uint(4)),
                (2, id.clone()),
                (3, V::Bytes(jb(signer, "kid")?)),
                (4, id),
            ]));
        }
        refs.sort_by_key(codec::encode);
        check(f(&bundle, 34)? == &V::Array(refs))?;
        let requirements = a(f(&policy, 5)?)?;
        check(requirements.len() == 1)?;
        let requirement = &requirements[0];
        exact(requirement, &[1, 2, 3, 4, 5, 6, 7, 8, 9, 10])?;
        check(
            f(requirement, 5)? == &V::Array(vec![V::Array(vec![V::Uint(4), V::Uint(3)])])
                && f(requirement, 9)? == &V::Bool(true),
        )?;
        check(
            f(requirement, 1)? == &text(GROUP)
                && n(requirement, 2)? == 3
                && n(requirement, 3)? == 5
                && f(requirement, 4)? == &V::Array(vec![V::Uint(4)])
                && f(requirement, 8)? == &V::Array(vec![V::Uint(12)])
                && f(requirement, 6)? == &V::Array(ids.into_iter().map(V::Bytes).collect())
                && n(requirement, 7)? == 3
                && f(requirement, 10)? == &h(f(&bundle, 32)?),
        )?;
        check(
            trust["governing_obligations"]
                .as_object()
                .is_some_and(|m| !m.is_empty() && m.values().all(|v| v == "satisfied-fixture")),
        )?;
        check(
            binding.service.as_slice() == b(f(f(&bundle, 32)?, 2)?)?
                && binding.operator.as_slice() == b(f(f(&bundle, 32)?, 4)?)?,
        )?;
        let inventory_bytes = jb(&trust, "dependency_inventory")?;
        let inventory = codec::decode_value(&inventory_bytes)?;
        let targets = a(&inventory)?;
        // A local supplied inventory, independently pinned with the context.
        // Neither the incoming record nor its caller can choose this membership.
        check(
            hash(&inventory_bytes) == binding.dependencies
                && !targets.is_empty()
                && targets.contains(&jv(&trust, "target")?)
                && targets
                    .windows(2)
                    .all(|w| codec::encode(&w[0]) < codec::encode(&w[1])),
        )?;
        check(
            ju(&trust, "required_witnesses")? == 2
                && trust["witnesses"].as_array().is_some_and(|w| w.len() == 3),
        )?;
        let log_ref = key_reference(&trust["log"], 5, 8, time)?;
        check(
            public_keys.insert(jb(&trust["log"], "key")?)
                && f(&bundle, 35)? == &V::Array(vec![log_ref]),
        )?;
        let mut witness_refs = Vec::new();
        let mut witness_ids = BTreeSet::new();
        let mut witness_kids = BTreeSet::new();
        let mut witness_orgs = BTreeSet::new();
        for key in trust["witnesses"].as_array().ok_or("witness inventory")? {
            witness_refs.push(key_reference(key, 6, 9, time)?);
            check(
                public_keys.insert(jb(key, "key")?)
                    && witness_ids.insert(jb(key, "id")?)
                    && witness_kids.insert(jb(key, "kid")?)
                    && witness_orgs.insert(
                        key["organization"]
                            .as_str()
                            .filter(|v| !v.is_empty())
                            .ok_or("witness organization")?,
                    )
                    && (16..=64).contains(&jb(key, "replay")?.len()),
            )?;
        }
        witness_refs.sort_by_key(codec::encode);
        check(
            f(&bundle, 36)? == &V::Array(witness_refs)
                && f(&bundle, 37)?
                    == &obj(vec![
                        (1, V::Array(vec![V::Uint(3), V::Uint(5)])),
                        (2, V::Array(vec![V::Uint(2), V::Uint(3)])),
                        (3, V::Array(vec![V::Uint(1), V::Uint(1)])),
                    ])
                && f(&bundle, 38)? == &V::Array(vec![V::Uint(1)])
                && n(&bundle, 40)? == ju(&trust, "maximum_staleness")?,
        )?;
        // These are explicitly supplied reference inventories, not verified genesis.
        for (field, class) in [(33, 1), (39, 14)] {
            let refs = a(f(&bundle, field)?)?;
            check(refs.len() == 1)?;
            exact(&refs[0], &[1, 2, 3, 4])?;
            check(
                n(&refs[0], 1)? == class
                    && b(f(&refs[0], 2)?)? == binding.operator
                    && b(f(&refs[0], 4)?)? == binding.operator
                    && (1..=64).contains(&b(f(&refs[0], 3)?)?.len()),
            )?;
        }
        let mut provider = Self {
            trust,
            policy,
            bundle,
            anchor,
            binding,
            identity: Arc::new(()),
            context: expected.to_vec(),
            revision: 1,
            last_time: 0,
            clock_failed: false,
            record: None,
            events: BTreeMap::new(),
        };
        provider.observe(time)?;
        provider.fresh(time)?;
        Ok(provider)
    }
    pub fn registration_ready(&self) -> bool {
        false
    }
    fn observe(&mut self, t: TimeWindow) -> Result<()> {
        if self.clock_failed
            || t.earliest > t.latest
            || t.latest > 253402300799
            || t.earliest < self.last_time
        {
            self.clock_failed = true;
            return Err("invalid/rolled-back clock");
        }
        self.last_time = t.earliest;
        Ok(())
    }
    fn fresh(&self, t: TimeWindow) -> Result<()> {
        check(
            n(&self.bundle, 6)? <= t.earliest
                && t.latest <= n(&self.bundle, 7)?
                && t.latest - n(&self.bundle, 6)? <= n(&self.bundle, 40)?,
        )
    }
    pub fn verify_normal_event(
        &mut self,
        raw: &[u8],
        owner: &Owner,
        t: TimeWindow,
    ) -> Result<VerifiedOwnerEvent> {
        self.observe(t)?;
        self.fresh(t)?;
        check(raw.len() <= 65536 && owner.binding == self.binding)?;
        let package = codec::decode_value(raw)?;
        exact(&package, &[1, 2, 3, 4, 5, 6, 7, 8, 9])?;
        check(n(&package, 1)? == 1 && f(&package, 2)? == &text(PROFILE))?;
        let record = b(f(&package, 3)?)?.to_vec();
        let r = codec::decode_value(&record)?;
        let keys = if map(&r)?.contains_key(&8) {
            vec![1, 2, 3, 4, 5, 6, 7, 8, 32, 33, 34, 35, 36, 37, 38, 39]
        } else {
            vec![1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39]
        };
        exact(&r, &keys)?;
        let effect = n(&r, 36)?;
        // Unchanged TypedRevocationRecord field contract, on original v2 bytes.
        check(
            n(&r, 34)? <= 31
                && n(&r, 4)? >= 1
                && n(&r, 5)? >= 1
                && n(&r, 6)? < n(&r, 7)?
                && n(&r, 7)? <= 253402300799
                && (f(&r, 35)? != &V::Bool(true) || n(&r, 7)? == 253402300799),
        )?;
        check(
            n(&r, 1)? == 13
                && n(&r, 2)? == 2
                && n(&r, 37)? == 2
                && matches!(effect, 1 | 4)
                && f(&r, 3)? == &jv(&self.trust, "issuer")?
                && f(&r, 32)? == &jv(&self.trust, "target")?
                && f(&r, 33)? == f(&self.bundle, 32)?
                && f(&r, 38)? == &V::Null
                && matches!(f(&r, 35)?, V::Bool(_))
                && n(&r, 6)? <= t.earliest
                && t.latest <= n(&r, 7)?,
        )?;
        let digest = hash(&record);
        let env = codec::decode_value(b(f(&package, 4)?)?)?;
        exact(&env, &[1, 2, 3, 4, 5, 6, 7, 8, 9])?;
        check(
            n(&env, 1)? == 1
                && f(&env, 2)? == &text(PROFILE)
                && n(&env, 3)? == 13
                && b(f(&env, 4)?)? == digest
                && f(&env, 5)? == &self.policy
                && f(&env, 6)? == &h(f(&r, 33)?),
        )?;
        check(
            f(&env, 7)?
                == &obj(vec![
                    (1, f(&r, 4)?.clone()),
                    (2, f(&r, 5)?.clone()),
                    (3, map(&r)?.get(&8).cloned().unwrap_or(V::Null)),
                ]),
        )?;
        let auth = f(&env, 8)?;
        exact(auth, &[1, 2, 3, 4, 5, 6, 7])?;
        let event = b(f(auth, 2)?)?.to_vec();
        check(
            (16..=64).contains(&event.len())
                && n(auth, 1)? == 16407
                && n(auth, 3)? <= t.earliest
                && t.latest <= n(auth, 4)?
                && n(auth, 6)? == 1
                && f(auth, 7)? == &text("deny"),
        )?;
        let mut unsigned = map(auth)?.clone();
        unsigned.remove(&5);
        check(f(auth, 5)? == &h(&V::Map(unsigned)))?;
        if let Some(previous) = self.events.get(&event) {
            check(previous == &digest)?;
        }
        let groups = a(f(&env, 9)?)?;
        check(groups.len() == 1)?;
        exact(&groups[0], &[1, 2])?;
        check(f(&groups[0], 1)? == &text(GROUP))?;
        let entries = a(f(&groups[0], 2)?)?;
        check((3..=5).contains(&entries.len()))?;
        let context = obj(vec![
            (1, text("NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1")),
            (2, V::Uint(1)),
            (3, text(PROFILE)),
            (4, V::Uint(13)),
            (5, V::Bytes(digest.clone())),
            (6, f(&self.policy, 2)?.clone()),
            (7, text(GROUP)),
            (8, f(&env, 6)?.clone()),
            (9, f(&env, 7)?.clone()),
            (10, auth.clone()),
            (11, V::Uint(6)),
            (12, V::Bytes(jb(&self.trust, "session_binding")?)),
        ]);
        // The opaque event must not outlive any evidence used to mint it.
        let mut expires = n(&r, 7)?.min(n(auth, 4)?);
        let mut seen = BTreeSet::new();
        let mut order = Vec::new();
        for entry in entries {
            exact(entry, &[1, 2, 3, 4, 5, 6, 7])?;
            let id = b(f(entry, 2)?)?;
            let kid = b(f(entry, 4)?)?;
            let signer = self.trust["signers"]
                .as_array()
                .ok_or("roster")?
                .iter()
                .find(|s| {
                    jb(s, "id").is_ok_and(|v| v == id) && jb(s, "kid").is_ok_and(|v| v == kid)
                })
                .ok_or("unknown signer")?;
            check(
                n(entry, 1)? == 4
                    && n(entry, 3)? == 12
                    && b(f(entry, 5)?)? == jb(signer, "organization")?
                    && f(entry, 6)? == f(&env, 4)?
                    && seen.insert(id.to_vec()),
            )?;
            check(signed(f(entry, 7)?, signer, t, 12)? == context)?;
            order.push((id.to_vec(), kid.to_vec()));
            expires = expires.min(ju(signer, "expires")?);
        }
        check(order.windows(2).all(|w| w[0] < w[1]))?;
        let log = &self.trust["log"];
        expires = expires.min(ju(log, "expires")?);
        let anchor = signed(f(&package, 9)?, log, t, 8)?;
        let checkpoint = signed(f(&package, 5)?, log, t, 8)?;
        let inclusion = signed(f(&package, 6)?, log, t, 8)?;
        let consistency = signed(f(&package, 7)?, log, t, 8)?;
        let duplicate = self.record.as_ref() == Some(&record);
        check(if duplicate {
            checkpoint == self.anchor
        } else {
            anchor == self.anchor
        })?;
        self.check_log(&anchor, t)?;
        self.check_current_checkpoint(&checkpoint, t)?;
        check(
            f(&r, 39)?
                == &obj(vec![
                    (1, f(&anchor, 32)?.clone()),
                    (2, h(&anchor)),
                    (3, f(&anchor, 34)?.clone()),
                    (4, V::Null),
                ]),
        )?;
        check(
            n(&checkpoint, 4)? == n(&anchor, 4)?
                && n(&checkpoint, 5)? == n(&anchor, 5)?.checked_add(1).ok_or("sequence")?
                && n(&checkpoint, 34)? > n(&anchor, 34)?
                && f(&checkpoint, 38)? == &h(&anchor),
        )?;
        self.check_proofs(&record, &anchor, &checkpoint, &inclusion, &consistency)?;
        let witnesses = a(f(&package, 8)?)?;
        check((2..=3).contains(&witnesses.len()))?;
        let mut witness_ids = BTreeSet::new();
        let mut witness_orgs = BTreeSet::new();
        let mut ordered = Vec::new();
        for wire in witnesses {
            // Try only the three pinned keys; never resolve identity from an untrusted claim.
            let mut found = None;
            for key in self.trust["witnesses"]
                .as_array()
                .ok_or("witness inventory")?
            {
                if let Ok(payload) = signed(wire, key, t, 9) {
                    found = Some((key, payload));
                    break;
                }
            }
            let (key, w) = found.ok_or("witness signature/purpose")?;
            exact(&w, &[1, 2, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42])?;
            let id = jb(key, "id")?;
            check(
                n(&w, 1)? == 9
                    && n(&w, 2)? == 1
                    && b(f(&w, 32)?)? == id
                    && f(&w, 33)? == f(&checkpoint, 32)?
                    && f(&w, 34)? == f(&checkpoint, 33)?
                    && f(&w, 35)? == &h(&checkpoint)
                    && f(&w, 36)? == f(&checkpoint, 34)?
                    && f(&w, 37)? == f(&checkpoint, 35)?
                    && n(&w, 38)? <= t.earliest
                    && t.latest <= n(&w, 42)?
                    && n(&w, 39)? == 1
                    && b(f(&w, 40)?)? == jb(key, "replay")?
                    && b(f(&w, 41)?)? == jb(key, "kid")?
                    && witness_ids.insert(id.clone())
                    && witness_orgs.insert(key["organization"].as_str().ok_or("organization")?),
            )?;
            expires = expires.min(ju(key, "expires")?).min(n(&w, 42)?);
            ordered.push(id);
        }
        check(ordered.windows(2).all(|w| w[0] < w[1]))?;
        if !duplicate {
            if let Some(old) = &self.record {
                let old = codec::decode_value(old)?;
                check(
                    f(&old, 35)? == &V::Bool(false)
                        && n(&r, 4)? == n(&old, 4)?
                        && n(&r, 5)? == n(&old, 5)?.checked_add(1).ok_or("sequence")?
                        && f(&r, 8)? == &h(&old),
                )?;
            } else {
                check(n(&r, 4)? == 1 && n(&r, 5)? == 1 && !map(&r)?.contains_key(&8))?;
            }
        }
        Ok(VerifiedOwnerEvent {
            provider: self.identity.clone(),
            revision: self.revision,
            owner: owner.clone(),
            context: self.context.clone(),
            record,
            event,
            checkpoint,
            effect,
            expires,
        })
    }
    fn check_log(&self, c: &V, t: TimeWindow) -> Result<()> {
        exact(c, &[1, 2, 3, 4, 5, 32, 33, 34, 35, 36, 37, 38, 39])?;
        let log = &self.trust["log"];
        let id = V::Bytes(jb(log, "id")?);
        let kid = V::Bytes(jb(log, "kid")?);
        check(
            n(c, 1)? == 6
                && n(c, 2)? == 1
                && f(c, 32)? == &id
                && f(c, 33)? == f(&self.bundle, 32)?
                && f(c, 37)? == &kid
                && f(c, 3)? == &obj(vec![(1, V::Uint(5)), (2, id.clone()), (3, kid), (4, id)])
                && f(c, 39)? == &V::Null
                && b(f(c, 35)?)?.len() == 32
                && n(c, 36)? <= t.earliest,
        )
    }
    fn check_current_checkpoint(&self, c: &V, t: TimeWindow) -> Result<()> {
        self.check_log(c, t)?;
        // The prior retained anchor is authenticated and identity-bound, but
        // freshness applies to the current containing checkpoint, as in Python.
        check(t.latest - n(c, 36)? <= ju(&self.trust, "maximum_staleness")?)
    }
    fn check_proofs(&self, record: &[u8], anchor: &V, c: &V, p: &V, s: &V) -> Result<()> {
        exact(p, &[1, 2, 32, 33, 34, 35, 36, 37, 38, 39, 40])?;
        exact(s, &[1, 2, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41])?;
        check(
            n(p, 1)? == 7
                && n(p, 2)? == 1
                && n(s, 1)? == 8
                && n(s, 2)? == 1
                && f(p, 32)? == f(c, 32)?
                && f(s, 32)? == f(c, 32)?
                && f(p, 33)? == f(c, 33)?
                && f(s, 33)? == f(c, 33)?
                && f(p, 34)? == &h(c)
                && f(p, 35)? == f(c, 34)?
                && n(p, 36)? == n(anchor, 34)?
                && n(p, 39)? == 1
                && n(p, 40)? == 13
                && f(s, 34)? == &h(anchor)
                && f(s, 35)? == &h(c)
                && f(s, 36)? == f(anchor, 34)?
                && f(s, 37)? == f(c, 34)?
                && f(s, 38)? == f(anchor, 35)?
                && f(s, 39)? == f(c, 35)?
                && n(s, 41)? == 1,
        )?;
        let mut leaf = vec![0];
        leaf.extend(record);
        let leaf = hash(&leaf);
        check(b(f(p, 37)?)? == leaf)?;
        // Explicit existing fixture horizon: empty->one and one->two leaves only.
        // No broader proof chain is treated as verified by this test-only slice.
        let root = match (n(anchor, 34)?, n(c, 34)?) {
            (0, 1) => {
                check(
                    a(f(p, 38)?)?.is_empty()
                        && a(f(s, 40)?)?.is_empty()
                        && b(f(anchor, 35)?)? == hash(&[]),
                )?;
                leaf
            }
            (1, 2) => {
                check(
                    a(f(p, 38)?)? == [f(anchor, 35)?.clone()]
                        && a(f(s, 40)?)? == [V::Bytes(leaf.clone())],
                )?;
                let mut joined = vec![1];
                joined.extend(b(f(anchor, 35)?)?);
                joined.extend(leaf);
                hash(&joined)
            }
            _ => return Err("unsupported local proof horizon"),
        };
        check(b(f(c, 35)?)? == root)
    }
    pub fn apply_verified_event(
        &mut self,
        gateway: &mut Gateway,
        event: VerifiedOwnerEvent,
        t: TimeWindow,
    ) -> Result<Applied> {
        self.observe(t)?;
        self.fresh(t)?;
        check(
            Arc::ptr_eq(&event.provider, &self.identity)
                && event.context == self.context
                && event.revision == self.revision
                && gateway.owner.as_ref() == Some(&event.owner)
                && t.latest <= event.expires,
        )?;
        self.check_current_checkpoint(&event.checkpoint, t)?;
        let digest = hash(&event.record);
        if self.events.get(&event.event) == Some(&digest) {
            return Ok(Applied::Idempotent);
        }
        check(!self.events.contains_key(&event.event) && self.events.len() < 4096)?;
        let revision = self.revision.checked_add(1).ok_or("revision exhaustion")?;
        if self.record.as_ref() == Some(&event.record) {
            // F=C was verified above. Retain the fresh event binding without
            // invoking cleanup/denial a second time or changing the floor.
            self.events.insert(event.event, digest);
            self.revision = revision;
            return Ok(Applied::Idempotent);
        }
        let ticket = gateway.apply_local_verified_effect(&event.owner, event.effect)?;
        self.events.insert(event.event, digest);
        self.record = Some(event.record);
        self.anchor = event.checkpoint;
        self.revision = revision;
        Ok(match ticket {
            Some(t) => Applied::Cleanup(Box::new(t)),
            None => Applied::Denied,
        })
    }
}
