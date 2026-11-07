use super::*;
const RAW: &[u8] = include_bytes!("../fixtures/connector-normal-kar-v2.json");
const PIN: &str = "54e6e22985c0ae5aef84ffaa72d4ce502dc5494df6cf9f977e6dd9bf9ca49fb0";
fn trust() -> serde_json::Value {
    serde_json::from_slice(RAW).unwrap()
}
fn v2(
    t: &serde_json::Value,
    b: Binding,
    time: TimeWindow,
) -> codec::Result<LocalAuthorityProvider> {
    let raw = serde_json::to_vec(t).unwrap();
    LocalAuthorityProvider::from_normal_roster_kar_test_trust(
        &raw,
        Sha256::digest(&raw).into(),
        b,
        time,
    )
}
#[test]
fn purpose12_positive_preserves_ids_and_old_signed_event() {
    assert_eq!(hex_string(&Sha256::digest(RAW)), PIN);
    let (mut g, _) = setup();
    let t = trust();
    assert_eq!(t["signers"], fixture()["trust"]["signers"]);
    assert_eq!(t["policy"], fixture()["trust"]["policy"]);
    assert!(
        t["normal_kar"]
            .as_array()
            .unwrap()
            .iter()
            .all(|j| j["authority"] != j["operator"])
    );
    let mut p = LocalAuthorityProvider::from_normal_roster_kar_test_trust(
        RAW,
        hex(PIN).try_into().unwrap(),
        g.owner.as_ref().unwrap().binding.clone(),
        clock(),
    )
    .unwrap();
    assert!(!p.registration_ready());
    let ev = p
        .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    assert!(matches!(
        p.apply_verified_event(&mut g, ev, clock()).unwrap(),
        Applied::Denied
    ));
}
#[test]
fn purpose12_versions_and_external_pin_are_separate() {
    let (g, _) = setup();
    let b = g.owner.as_ref().unwrap().binding.clone();
    assert!(
        LocalAuthorityProvider::from_normal_roster_kar_test_trust(RAW, [0; 32], b.clone(), clock())
            .is_err()
    );
    assert!(provider_for(&trust(), b.clone()).is_err());
    assert!(v2(&fixture()["trust"], b, clock()).is_err());
}
#[test]
fn purpose12_all_five_bindings_and_independence_are_required() {
    let (g, _) = setup();
    let b = g.owner.as_ref().unwrap().binding.clone();
    for i in 0..5 {
        for field in [
            "operator",
            "authority",
            "kid",
            "key",
            "organization",
            "control",
            "root",
            "payload",
            "wire",
        ] {
            let mut t = trust();
            t["normal_kar"][i][field] = t["normal_kar"][(i + 1) % 5][field].clone();
            assert!(
                v2(&t, b.clone(), clock()).is_err(),
                "member {i} swapped {field}"
            );
        }
        let mut t = trust();
        t["normal_kar"].as_array_mut().unwrap().remove(i);
        assert!(v2(&t, b.clone(), clock()).is_err(), "missing member {i}");
        for field in [
            "purpose", "key", "kid", "operator", "active", "revoked", "expires",
        ] {
            let mut t = trust();
            t["normal_kar"][i]["root"][field] = match field {
                "purpose" => 12.into(),
                "active" => false.into(),
                "revoked" => true.into(),
                "expires" => (clock().earliest - 1).into(),
                _ => "00".repeat(32).into(),
            };
            assert!(
                v2(&t, b.clone(), clock()).is_err(),
                "member {i} root {field}"
            );
        }
        let mut t = trust();
        let mut bytes = hex(t["normal_kar"][i]["wire"].as_str().unwrap());
        *bytes.last_mut().unwrap() ^= 1;
        t["normal_kar"][i]["wire"] = hex_string(&bytes).into();
        assert!(v2(&t, b.clone(), clock()).is_err(), "member {i} signature");
    }
    for field in ["id", "key", "organization", "control"] {
        let mut t = trust();
        t["signers"][4][field] = t["signers"][3][field].clone();
        assert!(v2(&t, b.clone(), clock()).is_err(), "duplicate {field}");
    }
}
#[test]
fn purpose12_unsigned_root_expiry_bounds_verification_and_apply() {
    for i in [3, 4] {
        let (mut g, _) = setup();
        let b = g.owner.as_ref().unwrap().binding.clone();
        let mut t = trust();
        t["normal_kar"][i]["root"]["not_before"] = clock().earliest.into();
        t["normal_kar"][i]["root"]["expires"] = (clock().earliest + 1).into();
        let mut p = v2(&t, b.clone(), clock()).unwrap();
        let end = TimeWindow {
            earliest: clock().earliest + 1,
            latest: clock().latest + 1,
        };
        let ev = p
            .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), end)
            .unwrap();
        let later = TimeWindow {
            earliest: end.earliest + 1,
            latest: end.latest + 1,
        };
        let before = g.owner.clone();
        assert!(p.apply_verified_event(&mut g, ev, later).is_err());
        assert_eq!(g.owner, before);
        assert!(
            p.verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), later)
                .is_err()
        );
        assert!(v2(&t, b, later).is_err());
    }
}
#[test]
fn purpose12_cross_context_event_keeps_owner() {
    let (mut g, mut old) = setup();
    let b = g.owner.as_ref().unwrap().binding.clone();
    let mut new = v2(&trust(), b, clock()).unwrap();
    let before = g.owner.clone();
    let ev = old
        .verify_normal_event(&wire("deny"), g.owner.as_ref().unwrap(), clock())
        .unwrap();
    assert!(new.apply_verified_event(&mut g, ev, clock()).is_err());
    assert_eq!(g.owner, before);
}
