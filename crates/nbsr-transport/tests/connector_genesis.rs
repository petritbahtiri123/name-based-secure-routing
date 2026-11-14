#![allow(dead_code)]
#[path = "../src/connector_control.rs"]
mod codec;
#[path = "support/connector_genesis.rs"]
mod genesis;
#[path = "support/connector_request_evidence.rs"]
mod request_evidence;
#[path = "../src/connector_kar.rs"]
mod kar;
#[path = "../src/connector_signature.rs"]
mod signature;

use genesis::{SignedInput, verify};
use kar::SuppliedTestRoot;
use serde_json::Value;

fn hex(s: &str) -> Vec<u8> {
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
        .collect()
}
fn corpus() -> Value {
    serde_json::from_str(include_str!("fixtures/connector-genesis-evidence.json")).unwrap()
}
#[test]
fn retained_signed_genesis_semantics_match_python_corpus() {
    let data = corpus();
    assert_eq!(data["runtime_authorized"], false);
    assert_eq!(data["live_trust_authorized"], false);
    assert_eq!(data["id"], "public-test-only-nor-direct-delegation-v1");
    let key: [u8; 32] = hex(data["public_key"].as_str().unwrap())
        .try_into()
        .unwrap();
    assert_eq!(
        data["public_key"],
        "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
    );
    let cases = data["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 13);
    let expected_ids = [
        "exact",
        "lower_boundary",
        "upper_boundary",
        "before_validity",
        "after_validity",
        "narrow_requested_port",
        "widen_requested_port",
        "widen_requested_protocol",
        "widen_requested_action",
        "wrong_genesis_service_id",
        "direct_parent_digest",
        "delegation_outlives_ownership",
        "revoked_delegation",
    ];
    assert_eq!(
        cases
            .iter()
            .map(|v| v["id"].as_str().unwrap())
            .collect::<Vec<_>>(),
        expected_ids
    );
    for case in cases {
        let expected_ok = [
            "exact",
            "lower_boundary",
            "upper_boundary",
            "narrow_requested_port",
        ]
        .contains(&case["id"].as_str().unwrap());
        assert_eq!(case["accepted"], expected_ok);
        let chain = case["chain"].as_array().unwrap();
        assert_eq!(chain.len(), 2);
        let signers: Vec<_> = chain
            .iter()
            .map(|v| SuppliedTestRoot {
                operator: hex(v["authority"]["operator_id"].as_str().unwrap())
                    .try_into()
                    .unwrap(),
                kid: b"key".to_vec(),
                key,
                purpose: v["authority"]["purpose"].as_u64().unwrap(),
                lifecycle: 2,
                generation: 1,
                sequence: 1,
                not_before: 800,
                expires: 2100,
                revoked: false,
            })
            .collect();
        let wires: Vec<_> = chain
            .iter()
            .map(|v| hex(v["wire"].as_str().unwrap()))
            .collect();
        let payloads: Vec<_> = chain
            .iter()
            .map(|v| hex(v["payload"].as_str().unwrap()))
            .collect();
        let inputs: Vec<_> = (0..2)
            .map(|i| SignedInput {
                wire: &wires[i],
                payload: &payloads[i],
                signer: &signers[i],
            })
            .collect();
        let result = verify(
            &inputs,
            &hex(case["request_scope"].as_str().unwrap()),
            case["now"].as_u64().unwrap(),
        );
        if case["accepted"] == true {
            let checked = result.unwrap_or_else(|e| panic!("{}: {:?}", case["id"], e));
            assert_eq!(checked.not_before, 900);
            assert_eq!(checked.expires, 1900); // Chain-only, not transport KAR1800.
            assert_eq!(
                checked.leaf_digest.as_slice(),
                hex(chain[1]["payload_sha256"].as_str().unwrap())
            );
        } else {
            assert!(
                matches!(result, Err(genesis::Reject::Invalid(_))),
                "{}: {:?}",
                case["id"],
                result
            );
        }
    }
}

// Parser-scope diagnostic only: these are unsigned CBOR text values, not
// signed ownership evidence or claims about normative federation validity.
#[test]
fn reused_connector_decoder_text_cap_bounds_native_evidence_subset() {
    for (lengths, expected_len, decodes) in [
        (vec![63, 62, 1], 128, true),
        (vec![63, 63, 1], 129, false),
        (vec![63, 63, 63, 63], 255, false),
    ] {
        let name = lengths
            .iter()
            .map(|n| "a".repeat(*n))
            .collect::<Vec<_>>()
            .join(".");
        assert_eq!(name.len(), expected_len);
        assert!(
            name.split('.')
                .all(|label| !label.is_empty() && label.len() <= 63)
        );
        let value = codec::Value::Text(name);
        let result = codec::decode_value(&codec::encode(&value));
        if decodes {
            assert_eq!(result.unwrap(), value);
        } else {
            assert!(
                result.is_err(),
                "native connector text cap changed at {expected_len}"
            );
        }
    }
}
