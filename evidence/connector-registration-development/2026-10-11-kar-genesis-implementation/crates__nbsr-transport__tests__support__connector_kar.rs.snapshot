use super::*;
use crate::codec::{decode_value, encode};
use serde_json::Value as J;

#[test]
fn existing_unsigned_transport_recipe_cannot_authorize_normal_revocation() {
    // Exact public payload recipe from test_connector_registration_authority_offline.py.
    // Reconstruct only unsigned fields; do not execute that module's signing helper.
    let (p, mut root, mut expected) = recipe();
    root.operator = [b'C'; 32];
    root.kid = b"key".to_vec();
    root.not_before = 800;
    expected.operator = root.operator;
    expected.kid = b"transport-key".to_vec();
    expected.key = root.key;
    expected.purpose = 14;
    let authority = V::Map(
        [
            (1, V::Uint(1)),
            (2, V::Bytes(root.operator.to_vec())),
            (3, V::Bytes(root.kid.clone())),
            (4, V::Bytes(root.operator.to_vec())),
        ]
        .into(),
    );
    let mut p = p;
    for (key, value) in [
        (3, authority.clone()),
        (6, V::Uint(900)),
        (7, V::Uint(1800)),
        (32, V::Bytes(expected.operator.to_vec())),
        (33, V::Bytes(expected.kid.clone())),
        (34, V::Bytes(expected.key.to_vec())),
        (35, V::Uint(14)),
        (37, authority),
    ] {
        p = changed(&p, key, Some(value));
    }
    assert!(semantics(&p, &root, &expected, 1000).is_ok());
    expected.purpose = 12;
    assert_eq!(
        semantics(&p, &root, &expected, 1000),
        Err("exact child purpose")
    );
}

fn hex(s: &str) -> Vec<u8> {
    s.as_bytes()
        .chunks_exact(2)
        .map(|c| u8::from_str_radix(std::str::from_utf8(c).unwrap(), 16).unwrap())
        .collect()
}
fn recipe() -> (Vec<u8>, SuppliedTestRoot, ExpectedKey) {
    let rows: J = serde_json::from_str(include_str!(
        "../../../../vectors/federation-v0.1-schema-proposal/literal-fixtures.json"
    ))
    .unwrap();
    let row = rows["fixtures"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["name"] == "valid-root-authorized-genesis")
        .unwrap();
    (
        hex(row["canonical_cbor_hex"].as_str().unwrap()),
        SuppliedTestRoot {
            operator: [b'O'; 32],
            kid: b"root-kid".to_vec(),
            key: hex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
                .try_into()
                .unwrap(),
            purpose: 1,
            lifecycle: 2,
            generation: 1,
            sequence: 1,
            not_before: 900,
            expires: 2100,
            revoked: false,
        },
        ExpectedKey {
            operator: [b'O'; 32],
            kid: b"operational-kid".to_vec(),
            key: [b'K'; 32],
            purpose: 3,
            terminal_ids: vec![],
        },
    )
}
fn changed(raw: &[u8], key: u64, value: Option<V>) -> Vec<u8> {
    let mut m = map(&decode_value(raw).unwrap()).unwrap().clone();
    match value {
        Some(v) => {
            m.insert(key, v);
        }
        None => {
            m.remove(&key);
        }
    }
    encode(&V::Map(m))
}

#[test]
fn semantic_recipe_inclusive_child_and_root_boundaries() {
    let (p, r, e) = recipe();
    for t in [1000, 1500, 2000] {
        assert!(semantics(&p, &r, &e, t).is_ok());
    }
    for t in [999, 2001, u64::MAX] {
        assert!(semantics(&p, &r, &e, t).is_err(), "child time {t}");
    }
    let mut root = r;
    root.not_before = 1100;
    root.expires = 1900;
    for t in [1100, 1900] {
        assert!(semantics(&p, &root, &e, t).is_ok());
    }
    for t in [1099, 1901] {
        assert!(semantics(&p, &root, &e, t).is_err(), "root time {t}");
    }
}
#[test]
fn supplied_root_identity_purpose_state_and_lineage_reject() {
    let (p, r, e) = recipe();
    let mut bad = Vec::new();
    for purpose in [0, 2, 3, 12, 14, 17] {
        let mut x = r.clone();
        x.purpose = purpose;
        bad.push(x);
    }
    for lifecycle in [0, 1, 3, 4, 5, 6] {
        let mut x = r.clone();
        x.lifecycle = lifecycle;
        bad.push(x);
    }
    let mut x = r.clone();
    x.revoked = true;
    bad.push(x);
    let mut x = r.clone();
    x.operator[0] ^= 1;
    bad.push(x);
    for kid in [vec![], vec![1; 65], b"other".to_vec()] {
        let mut x = r.clone();
        x.kid = kid;
        bad.push(x);
    }
    let mut x = r.clone();
    x.generation = 0;
    bad.push(x);
    let mut x = r.clone();
    x.sequence = 0;
    bad.push(x);
    let mut x = r.clone();
    x.not_before = x.expires;
    bad.push(x);
    let mut x = r;
    x.expires = 253402300800;
    bad.push(x);
    for (i, x) in bad.iter().enumerate() {
        assert!(semantics(&p, x, &e, 1500).is_err(), "root variant {i}");
    }
}
#[test]
fn exact_child_identity_purpose_and_terminal_inventory_reject() {
    let (p, r, e) = recipe();
    let mut bad = Vec::new();
    for purpose in [0, 1, 12, 14, 17] {
        let mut x = e.clone();
        x.purpose = purpose;
        bad.push(x);
    }
    let mut x = e.clone();
    x.operator[0] ^= 1;
    bad.push(x);
    let mut x = e.clone();
    x.key[0] ^= 1;
    bad.push(x);
    for kid in [vec![], vec![1; 65], b"other".to_vec()] {
        let mut x = e.clone();
        x.kid = kid;
        bad.push(x);
    }
    let mut x = e;
    x.terminal_ids.push(x.kid.clone());
    bad.push(x);
    for (i, x) in bad.iter().enumerate() {
        assert!(semantics(&p, &r, x, 1500).is_err(), "expected variant {i}");
    }
}
#[test]
fn genesis_only_closed_schema_state_and_types_reject() {
    let (p, r, e) = recipe();
    for key in [1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39] {
        assert!(
            semantics(&changed(&p, key, None), &r, &e, 1500).is_err(),
            "missing {key}"
        );
    }
    for (key, value) in [
        (1, V::Uint(1)),
        (2, V::Bool(true)),
        (4, V::Uint(2)),
        (5, V::Uint(2)),
        (4, V::Bool(true)),
        (6, V::Bool(false)),
        (7, V::Uint(1000)),
        (7, V::Uint(253402300800)),
        (8, V::Bytes(vec![0; 32])),
        (40, V::Bytes(vec![0; 32])),
        (99, V::Null),
        (32, V::Bytes(vec![0; 31])),
        (33, V::Bytes(vec![])),
        (34, V::Bytes(vec![0; 31])),
        (35, V::Uint(12)),
        (35, V::Bool(true)),
        (36, V::Uint(1)),
        (36, V::Uint(3)),
        (36, V::Uint(4)),
        (36, V::Uint(5)),
        (38, V::Bool(true)),
        (38, V::Uint(0)),
        (39, V::Uint(0)),
    ] {
        assert!(
            semantics(&changed(&p, key, Some(value)), &r, &e, 1500).is_err(),
            "field {key}"
        );
    }
}
#[test]
fn authorizer_is_exact_but_issuer_only_has_existing_schema_checks() {
    let (p, r, e) = recipe();
    let decoded = decode_value(&p).unwrap();
    let authorizer = map(map(&decoded).unwrap().get(&37).unwrap()).unwrap();
    for (key, value) in [
        (1, V::Uint(2)),
        (2, V::Bytes(vec![b'X'; 32])),
        (3, V::Null),
        (4, V::Null),
    ] {
        let mut m = authorizer.clone();
        m.insert(key, value);
        assert!(semantics(&changed(&p, 37, Some(V::Map(m))), &r, &e, 1500).is_err());
    }
    let mut issuer = authorizer.clone();
    issuer.insert(3, V::Null);
    assert!(semantics(&changed(&p, 3, Some(V::Map(issuer))), &r, &e, 1500).is_ok());
    assert!(semantics(&changed(&p, 3, Some(V::Null)), &r, &e, 1500).is_err());
}
#[test]
fn bounded_noncritical_extensions_only_and_canonical_payload() {
    let (p, r, e) = recipe();
    let extension = |critical| {
        V::Map(
            [(
                1000,
                V::Map(
                    [
                        (1, V::Uint(1)),
                        (2, V::Bool(critical)),
                        (3, V::Bytes(vec![])),
                    ]
                    .into(),
                ),
            )]
            .into(),
        )
    };
    assert!(semantics(&changed(&p, 31, Some(extension(false))), &r, &e, 1500).is_ok());
    assert!(semantics(&changed(&p, 31, Some(extension(true))), &r, &e, 1500).is_err());
    assert!(semantics(&changed(&p, 31, Some(V::Null)), &r, &e, 1500).is_err());
    let mut trailing = p.clone();
    trailing.push(0);
    for raw in [vec![], vec![0; 32769], trailing] {
        assert!(semantics(&raw, &r, &e, 1500).is_err());
    }
}
#[test]
fn unchanged_signed_fixtures_do_not_supply_composed_positive_acceptance() {
    let rows: J = serde_json::from_str(include_str!(
        "../fixtures/connector-signature-primitives.json"
    ))
    .unwrap();
    for name in [
        "signed-04-valid-root-authorized-genesis",
        "signed-05-valid-rotation-update",
        "signed-06-valid-recovery-authorized-new-generation",
        "signed-negative-wrong-key-purpose",
    ] {
        let row = rows["cases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["name"] == name)
            .unwrap();
        let p = hex(row["payload"].as_str().unwrap());
        let wire = hex(row["wire"].as_str().unwrap());
        let v = decode_value(&p).unwrap();
        let m = map(&v).unwrap();
        let raw = |k| match m.get(&k).unwrap() {
            V::Bytes(x) => x.clone(),
            _ => panic!(),
        };
        let retained: J = serde_json::from_str(include_str!(
            "../../../../vectors/federation-v0.1/signed-vectors.json"
        ))
        .unwrap();
        let trust = retained["trusted_signers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|t| t["kid"] == row["kid"])
            .unwrap();
        let root = SuppliedTestRoot {
            operator: hex(trust["operator_id"].as_str().unwrap())
                .try_into()
                .unwrap(),
            kid: hex(trust["kid"].as_str().unwrap()),
            key: hex(trust["signing_public_key"].as_str().unwrap())
                .try_into()
                .unwrap(),
            purpose: trust["key_purpose"].as_u64().unwrap(),
            lifecycle: trust["key_lifecycle"].as_u64().unwrap(),
            generation: trust["generation"].as_u64().unwrap(),
            sequence: trust["sequence"].as_u64().unwrap(),
            not_before: trust["not_before"].as_u64().unwrap(),
            expires: trust["expires_at"].as_u64().unwrap(),
            revoked: trust["revoked"].as_bool().unwrap(),
        };
        let e = ExpectedKey {
            operator: raw(32).try_into().unwrap(),
            kid: raw(33),
            key: raw(34).try_into().unwrap(),
            purpose: 3,
            terminal_ids: vec![],
        };
        assert!(signature::verify_exact(&wire, &p, &root.kid, &root.key).is_ok());
        for t in [1000, 2000, 1900000000] {
            assert!(
                verify_genesis(&wire, &p, &root, &e, t).is_err(),
                "{name} at {t}"
            );
        }
        let mut corrupt = wire.clone();
        *corrupt.last_mut().unwrap() ^= 1;
        assert_eq!(
            verify_genesis(&corrupt, &p, &root, &e, 1900000000).err(),
            Some("invalid signature")
        );
        let mut wrong_payload = p.clone();
        wrong_payload[0] ^= 1;
        assert_eq!(
            verify_genesis(&wire, &wrong_payload, &root, &e, 1900000000).err(),
            Some("signature payload context mismatch")
        );
        let mut wrong_root = root.clone();
        wrong_root.kid[0] ^= 1;
        assert_eq!(
            verify_genesis(&wire, &p, &wrong_root, &e, 1900000000).err(),
            Some("exact protected headers and empty unprotected map required")
        );
    }
}
