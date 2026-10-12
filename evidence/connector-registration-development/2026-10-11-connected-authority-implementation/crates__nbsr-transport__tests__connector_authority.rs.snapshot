#[path = "../src/connector_authority.rs"]
mod authority;
#[path = "../src/connector_cleanup.rs"]
#[allow(dead_code)] // This target exercises only the connected authority seam.
mod cleanup;
#[path = "../src/connector_control.rs"]
#[allow(dead_code)]
mod codec;
#[path = "../src/connector_registration.rs"]
#[allow(dead_code)]
mod owner;
#[path = "../src/connector_signature.rs"]
#[allow(dead_code)]
mod signature;
use authority::{Applied, LocalAuthorityProvider, TimeWindow};
use codec::{Value as V, bytes, get, map};
use owner::{Binding, Gateway, Owner};
use sha2::{Digest, Sha256};

fn fixture() -> serde_json::Value {
    serde_json::from_str(include_str!(
        "../../../vectors/connector-authority-local-v1/cases.json"
    ))
    .unwrap()
}
fn hex(s: &str) -> Vec<u8> {
    s.as_bytes()
        .chunks_exact(2)
        .map(|v| u8::from_str_radix(std::str::from_utf8(v).unwrap(), 16).unwrap())
        .collect()
}
fn wire(name: &str) -> Vec<u8> {
    hex(fixture()["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["name"] == name)
        .unwrap()["wire"]
        .as_str()
        .unwrap())
}
fn clock() -> TimeWindow {
    TimeWindow {
        earliest: 1750000100,
        latest: 1750000100,
    }
}
fn setup() -> (Gateway, LocalAuthorityProvider) {
    setup_with(|_| {})
}
fn setup_with(change: impl FnOnce(&mut serde_json::Value)) -> (Gateway, LocalAuthorityProvider) {
    let raw = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/connector-registration-development-v1/request.cbor"),
    )
    .unwrap();
    let envelope = codec::decode(codec::ALPN, &raw).unwrap();
    let mut request = get(map(&envelope).unwrap(), 5).unwrap().clone();
    if let V::Map(fields) = &mut request {
        fields.insert(3, V::Bytes(vec![b'S'; 32]));
        fields.insert(4, V::Bytes(vec![b'O'; 32]));
        let inventory = hex(fixture()["trust"]["dependency_inventory"].as_str().unwrap());
        fields.insert(12, V::Bytes(Sha256::digest(inventory).to_vec()));
    }
    let fields = map(&request).unwrap();
    let b32 = |k| -> [u8; 32] {
        bytes(get(fields, k).unwrap(), 32, false)
            .unwrap()
            .try_into()
            .unwrap()
    };
    let gateway = if let V::Text(s) = get(fields, 6).unwrap() {
        s.clone()
    } else {
        panic!()
    };
    let mut g = Gateway::new(request.clone(), [8; 16], 0).unwrap();
    g.attach(1, [b's'; 16], b32(8), clock().earliest).unwrap();
    // Explicit synthetic owner setup, NOT an admission by the new provider.
    g.owner = Some(Owner {
        binding: Binding {
            profile: "connector-registration-development-v1".into(),
            action: 24576,
            connection: 1,
            session: [b's'; 16],
            peer: b32(8),
            service: b32(3),
            gateway,
            operator: b32(4),
            digest: Sha256::digest(codec::encode(&request)).into(),
            dependencies: b32(12),
            policy: b32(5),
        },
        registration: [1; 16],
        generation: 1,
        expires: 1750000300,
        digest: [9; 32],
        eligible: true,
    });
    let mut trust = fixture()["trust"].clone();
    change(&mut trust);
    let data = serde_json::to_vec(&trust).unwrap();
    let pin = Sha256::digest(&data).into(); // Test caller explicitly supplies this trust, not a network pin.
    let provider = LocalAuthorityProvider::from_supplied_test_trust(
        &data,
        pin,
        g.owner.as_ref().unwrap().binding.clone(),
        clock(),
    )
    .unwrap();
    (g, provider)
}

fn provider_for(
    trust: &serde_json::Value,
    binding: Binding,
) -> codec::Result<LocalAuthorityProvider> {
    let data = serde_json::to_vec(trust).unwrap();
    LocalAuthorityProvider::from_supplied_test_trust(
        &data,
        Sha256::digest(&data).into(),
        binding,
        clock(),
    )
}

#[test]
fn supplied_dependency_inventory_must_bind_exact_owner_and_target() {
    let (g, _) = setup();
    let binding = g.owner.as_ref().unwrap().binding.clone();
    let trust = fixture()["trust"].clone();
    let mut wrong = binding.clone();
    wrong.dependencies = [99; 32];
    assert!(
        provider_for(&trust, wrong).is_err(),
        "unrelated dependency digest"
    );
    let mut wrong_trust = trust.clone();
    let unrelated = codec::encode(&V::Array(vec![]));
    wrong_trust["dependency_inventory"] = hex_string(&unrelated).into();
    let mut wrong = binding;
    wrong.dependencies = Sha256::digest(unrelated).into();
    assert!(
        provider_for(&wrong_trust, wrong).is_err(),
        "target absent from inventory"
    );
}

fn hex_string(raw: &[u8]) -> String {
    raw.iter().map(|b| format!("{b:02x}")).collect()
}

fn change_cbor(trust: &mut serde_json::Value, name: &str, change: impl FnOnce(&mut V)) {
    let mut value = codec::decode_value(&hex(trust[name].as_str().unwrap())).unwrap();
    change(&mut value);
    let raw = codec::encode(&value);
    trust[name] = hex_string(&raw).into();
    if name == "bundle" {
        trust["bundle_digest"] = hex_string(&Sha256::digest(&raw)).into();
    }
}

#[test]
fn inconsistent_supplied_configuration_is_rejected_even_when_repinned() {
    let (g, _) = setup();
    let mut accepted = Vec::new();
    for case in [
        "logs",
        "witnesses",
        "thresholds",
        "profiles",
        "roots",
        "controllers",
        "staleness",
        "classes",
        "messages",
        "effects",
        "required",
        "class_minimum",
        "independence",
        "signer_key_alias",
        "witness_key_alias",
    ] {
        let mut trust = fixture()["trust"].clone();
        match case {
            "signer_key_alias" => trust["signers"][1]["key"] = trust["signers"][0]["key"].clone(),
            "witness_key_alias" => {
                trust["witnesses"][1]["key"] = trust["witnesses"][0]["key"].clone()
            }
            "classes" | "messages" | "effects" | "required" | "class_minimum" | "independence" => {
                change_cbor(&mut trust, "policy", |value| {
                    let V::Map(fields) = value else { panic!() };
                    match case {
                        "classes" => {
                            fields.insert(6, V::Array(vec![V::Uint(5)]));
                        }
                        "messages" => {
                            fields.insert(7, V::Array(vec![V::Uint(1)]));
                        }
                        "effects" => {
                            fields.insert(9, V::Array(vec![V::Text("allow".into())]));
                        }
                        "required" => {
                            fields.insert(4, V::Bool(false));
                        }
                        _ => {
                            let V::Array(groups) = fields.get_mut(&5).unwrap() else {
                                panic!()
                            };
                            let V::Map(group) = &mut groups[0] else {
                                panic!()
                            };
                            if case == "class_minimum" {
                                group.insert(5, V::Array(vec![]));
                            } else {
                                group.insert(9, V::Bool(false));
                            }
                        }
                    }
                    fields.insert(2, V::Null);
                    let digest = Sha256::digest(codec::encode(&V::Map(fields.clone()))).to_vec();
                    fields.insert(2, V::Bytes(digest));
                });
                let policy = codec::decode_value(&hex(trust["policy"].as_str().unwrap())).unwrap();
                change_cbor(&mut trust, "bundle", |value| {
                    let V::Map(fields) = value else { panic!() };
                    fields.insert(41, get(map(&policy).unwrap(), 2).unwrap().clone());
                });
            }
            _ => change_cbor(&mut trust, "bundle", |value| {
                let V::Map(fields) = value else { panic!() };
                let key = match case {
                    "logs" => 35,
                    "witnesses" => 36,
                    "thresholds" => 37,
                    "profiles" => 38,
                    "roots" => 33,
                    "controllers" => 39,
                    "staleness" => 40,
                    _ => unreachable!(),
                };
                fields.insert(
                    key,
                    if case == "staleness" {
                        V::Uint(901)
                    } else {
                        V::Array(vec![])
                    },
                );
            }),
        }
        if provider_for(&trust, g.owner.as_ref().unwrap().binding.clone()).is_ok() {
            accepted.push(case);
        }
    }
    assert!(
        accepted.is_empty(),
        "inconsistent contexts accepted: {accepted:?}"
    );
}

#[test]
fn signed_malformed_records_reject_without_owner_mutation() {
    let mut accepted = Vec::new();
    for name in [
        "finite-terminal",
        "invalid-reason",
        "boolean-reason",
        "zero-validity",
        "timestamp-overflow",
    ] {
        let (g, mut p) = setup();
        let before = g.owner.clone();
        if p.verify_normal_event(&wire(name), g.owner.as_ref().unwrap(), clock())
            .is_ok()
        {
            accepted.push(name);
        }
        assert_eq!(g.owner, before);
    }
    assert!(
        accepted.is_empty(),
        "signed malformed records accepted: {accepted:?}"
    );
}

#[test]
fn fresh_event_for_same_record_retains_binding_without_reapplying_effect() {
    for row in fixture()["replays"].as_array().unwrap() {
        let (mut g, mut p) = setup();
        let first = hex(row["first"].as_str().unwrap());
        let fresh = hex(row["fresh"].as_str().unwrap());
        let event = p
            .verify_normal_event(&first, g.owner.as_ref().unwrap(), clock())
            .unwrap();
        let applied = p.apply_verified_event(&mut g, event, clock()).unwrap();
        let before = g.owner.clone();
        let event = p
            .verify_normal_event(&fresh, g.owner.as_ref().unwrap(), clock())
            .unwrap();
        assert!(matches!(
            p.apply_verified_event(&mut g, event, clock()).unwrap(),
            Applied::Idempotent
        ));
        assert_eq!(g.owner, before);
        // The same fresh binding also retries idempotently. A pending cleanup
        // remains owned by its original ticket, with no second close attempt.
        let event = p
            .verify_normal_event(&fresh, g.owner.as_ref().unwrap(), clock())
            .unwrap();
        assert!(matches!(
            p.apply_verified_event(&mut g, event, clock()).unwrap(),
            Applied::Idempotent
        ));
        if let Applied::Cleanup(ticket) = applied {
            ticket.complete(Ok(()));
            g.finish_cleanup(&ticket).unwrap();
            assert!(g.owner.is_none());
        }
    }
}

#[test]
fn final_apply_rechecks_all_selected_evidence_deadlines() {
    // Existing signed witness statements expire at 1750000200.
    for boundary in [1750000200, 1750000201] {
        let (mut g, mut p) = setup();
        let event = p
            .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
            .unwrap();
        let before = g.owner.clone();
        let result = p.apply_verified_event(
            &mut g,
            event,
            TimeWindow {
                earliest: boundary,
                latest: boundary,
            },
        );
        assert_eq!(
            result.is_ok(),
            boundary == 1750000200,
            "witness statement boundary {boundary}"
        );
        if result.is_err() {
            assert_eq!(g.owner, before);
        }
    }
    for role in ["signers", "log", "witnesses"] {
        for boundary in [1750000101, 1750000102] {
            let (mut g, mut p) = setup_with(|trust| {
                if role == "log" {
                    trust[role]["expires"] = 1750000101u64.into();
                } else {
                    for row in trust[role].as_array_mut().unwrap() {
                        row["expires"] = 1750000101u64.into();
                    }
                }
            });
            let event = p
                .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
                .unwrap();
            let before = g.owner.clone();
            let result = p.apply_verified_event(
                &mut g,
                event,
                TimeWindow {
                    earliest: boundary,
                    latest: boundary,
                },
            );
            assert_eq!(
                result.is_ok(),
                boundary == 1750000101,
                "{role} deadline {boundary}"
            );
            if result.is_err() {
                assert_eq!(g.owner, before);
            }
        }
    }
}

#[test]
fn native_cases_match_independent_oracle_without_positive_authority() {
    for row in fixture()["cases"].as_array().unwrap() {
        let (g, mut p) = setup_with(|trust| {
            if let Some(anchor) = row.get("supplied_anchor") {
                trust["anchor"] = anchor.clone();
            }
        });
        assert!(!p.registration_ready());
        let result = p.verify_normal_event(
            &hex(row["wire"].as_str().unwrap()),
            g.owner.as_ref().unwrap(),
            clock(),
        );
        assert_eq!(
            result.is_ok(),
            row["accepted"].as_bool().unwrap(),
            "{}: {:?}",
            row["name"],
            result.err()
        );
    }
}

#[test]
fn old_retained_anchor_accepts_fresh_containing_checkpoint() {
    let row = fixture()["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["name"] == "old-retained-anchor")
        .unwrap()
        .clone();
    assert_eq!(row["accepted"], true);
    let (mut g, mut p) = setup_with(|t| t["anchor"] = row["supplied_anchor"].clone());
    let event = p
        .verify_normal_event(
            &wire("old-retained-anchor"),
            g.owner.as_ref().unwrap(),
            clock(),
        )
        .unwrap();
    assert!(matches!(
        p.apply_verified_event(&mut g, event, clock()).unwrap(),
        Applied::Cleanup(_)
    ));
}
#[test]
fn verified_termination_retains_owner_until_exact_confirmation() {
    let (mut g, mut p) = setup();
    let event = p
        .verify_normal_event(&wire("terminate"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    let Applied::Cleanup(ticket) = p.apply_verified_event(&mut g, event, clock()).unwrap() else {
        panic!()
    };
    assert!(g.owner.is_some());
    assert!(!g.owner.as_ref().unwrap().eligible);
    assert!(g.finish_cleanup(&ticket).is_err());
    ticket.complete(Err("synthetic failure"));
    assert!(g.finish_cleanup(&ticket).is_err());
    let retry = g.retry_cleanup(&ticket).unwrap();
    retry.complete(Ok(()));
    assert!(g.finish_cleanup(&ticket).is_err());
    g.finish_cleanup(&retry).unwrap();
    assert!(g.owner.is_none());
}
#[test]
fn deny_new_retains_owner_and_retry_is_idempotent() {
    let (mut g, mut p) = setup();
    let event = p
        .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    assert!(matches!(
        p.apply_verified_event(&mut g, event, clock()).unwrap(),
        Applied::Denied
    ));
    assert!(g.owner.is_some());
    assert!(!g.owner.as_ref().unwrap().eligible);
    let event = p
        .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    assert!(matches!(
        p.apply_verified_event(&mut g, event, clock()).unwrap(),
        Applied::Idempotent
    ));
}
#[test]
fn wrong_owner_after_verification_cannot_mutate_replacement() {
    let (mut g, mut p) = setup();
    let event = p
        .verify_normal_event(&wire("terminate"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    g.owner.as_mut().unwrap().generation += 1;
    let before = g.owner.clone();
    assert!(p.apply_verified_event(&mut g, event, clock()).is_err());
    assert_eq!(g.owner, before);
}

#[test]
fn changed_session_request_dependency_or_provider_cannot_apply() {
    for field in ["session", "request", "dependency", "provider", "revision"] {
        let (mut g, mut p) = setup();
        let event = p
            .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
            .unwrap();
        match field {
            "session" => g.owner.as_mut().unwrap().binding.session = [44; 16],
            "request" => g.owner.as_mut().unwrap().binding.digest = [44; 32],
            "dependency" => g.owner.as_mut().unwrap().binding.dependencies = [44; 32],
            "provider" => p = setup().1,
            "revision" => {
                let other = p
                    .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
                    .unwrap();
                p.apply_verified_event(&mut g, other, clock()).unwrap();
                // Restore the exact synthetic owner snapshot to isolate revision.
                g.owner.as_mut().unwrap().eligible = true;
            }
            _ => unreachable!(),
        }
        let before = g.owner.clone();
        assert!(
            p.apply_verified_event(&mut g, event, clock()).is_err(),
            "{field}"
        );
        assert_eq!(g.owner, before);
    }
}

#[test]
fn retained_fresh_event_rejects_rebinding_to_another_signed_record() {
    let value = fixture();
    let pairs = value["replays"].as_array().unwrap();
    let (mut g, mut p) = setup();
    for name in ["first", "fresh"] {
        let event = p
            .verify_normal_event(
                &hex(pairs[0][name].as_str().unwrap()),
                g.owner.as_ref().unwrap(),
                clock(),
            )
            .unwrap();
        p.apply_verified_event(&mut g, event, clock()).unwrap();
    }
    let before = g.owner.clone();
    assert!(
        p.verify_normal_event(
            &hex(pairs[1]["fresh"].as_str().unwrap()),
            g.owner.as_ref().unwrap(),
            clock()
        )
        .is_err()
    );
    assert_eq!(g.owner, before);
}
#[test]
fn stale_clock_and_bad_evidence_preserve_owner() {
    let (mut g, mut p) = setup();
    let before = g.owner.clone();
    assert!(
        p.verify_normal_event(&wire("bad-signature"), g.owner.as_ref().unwrap(), clock())
            .is_err()
    );
    assert!(
        p.verify_normal_event(
            &wire("deny"),
            g.owner.as_ref().unwrap(),
            TimeWindow {
                earliest: 1750000500,
                latest: 1750000500
            }
        )
        .is_err()
    );
    assert_eq!(g.owner, before);
    let (_, mut p) = setup();
    let event = p
        .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    assert!(
        p.apply_verified_event(
            &mut g,
            event,
            TimeWindow {
                earliest: 99,
                latest: 99
            }
        )
        .is_err()
    );
    assert_eq!(g.owner, before);
}
