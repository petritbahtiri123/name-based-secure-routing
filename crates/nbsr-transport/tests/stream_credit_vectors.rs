use std::fs;
use std::path::PathBuf;

use nbsr_transport::{
    StreamCreditContext, StreamCreditPreface, StreamCreditProfile, StreamCreditReject,
    decode_stream_credit_preface, encode_stream_credit_preface,
};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

const CHANNEL_ID: [u8; 16] = [
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f,
];
const SESSION_ID: [u8; 16] = [
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f,
];

// This would fail if the codec emitted an unbounded/non-canonical preface or
// accepted the preface as a bearer token instead of binding it to local state.
fn context() -> StreamCreditContext {
    StreamCreditContext {
        session_id: SESSION_ID,
        authenticated_session_id: SESSION_ID,
        channel_id: CHANNEL_ID,
        channel_generation: 1,
        quic_stream_id: 4,
    }
}

fn valid_preface() -> Vec<u8> {
    vector("valid/slot-0.cbor")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("vectors/stream-credit-v1");
    fs::read(root.join(relative)).expect("checked-in stream-credit fixture")
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn selects_the_exact_profile_and_never_automatically_falls_back() {
    assert_eq!(
        StreamCreditProfile::select(true, Some("nbsr-stream-credit-1"), false),
        Ok(StreamCreditProfile::V1),
    );
    assert_eq!(
        StreamCreditProfile::select(true, Some("nbsr-stream-credit-2"), false),
        Err(StreamCreditReject::ProfileUnsupported),
    );
    assert_eq!(
        StreamCreditProfile::select(true, None, false),
        Err(StreamCreditReject::Downgrade),
    );
    assert_eq!(
        StreamCreditProfile::select(true, None, true),
        Err(StreamCreditReject::FallbackForbidden),
    );
    assert_eq!(
        StreamCreditProfile::select(false, None, true),
        Ok(StreamCreditProfile::Legacy),
    );
}

#[test]
fn decodes_the_fixed_valid_preface_and_encodes_it_byte_exactly() {
    let expected = StreamCreditPreface {
        channel_id: CHANNEL_ID,
        channel_generation: 1,
        credit_epoch: 1,
        credit_slot: 0,
        quic_stream_id: 4,
    };
    assert_eq!(
        decode_stream_credit_preface(&valid_preface(), context()),
        Ok(expected)
    );
    assert_eq!(encode_stream_credit_preface(&expected), Ok(valid_preface()));
}

#[test]
fn rejects_malformed_prefices_and_out_of_range_slots_before_admission() {
    assert_eq!(
        vector("invalid/malformed-indefinite.cbor"),
        vec![0x02, 0xbf, 0xff],
        "the malformed vector must frame one indefinite CBOR item exactly"
    );
    assert_eq!(
        decode_stream_credit_preface(&vector("invalid/malformed-indefinite.cbor"), context()),
        Err(StreamCreditReject::MalformedPreface),
    );
    assert_eq!(
        decode_stream_credit_preface(&vector("invalid/slot-64.cbor"), context()),
        Err(StreamCreditReject::InvalidSlot),
    );
}

#[test]
fn decoder_derives_binding_rejections_from_bytes_and_authenticated_context() {
    assert_eq!(
        decode_stream_credit_preface(&vector("invalid/wrong-channel.cbor"), context()),
        Err(StreamCreditReject::WrongChannel),
    );

    assert_eq!(
        decode_stream_credit_preface(&vector("invalid/wrong-generation.cbor"), context()),
        Err(StreamCreditReject::WrongGeneration),
    );

    assert_eq!(
        decode_stream_credit_preface(&vector("invalid/zero-epoch.cbor"), context()),
        Err(StreamCreditReject::MalformedPreface),
    );

    assert_eq!(
        decode_stream_credit_preface(&vector("valid/slot-63.cbor"), context()),
        Ok(StreamCreditPreface {
            channel_id: CHANNEL_ID,
            channel_generation: 1,
            credit_epoch: 1,
            credit_slot: 63,
            quic_stream_id: 4,
        }),
    );

    assert_eq!(
        decode_stream_credit_preface(&vector("invalid/wrong-stream.cbor"), context()),
        Err(StreamCreditReject::WrongStream),
    );

    let mut wrong_session = context();
    wrong_session.authenticated_session_id[0] ^= 0x01;
    assert_eq!(
        decode_stream_credit_preface(&valid_preface(), wrong_session),
        Err(StreamCreditReject::WrongSession),
    );
}

#[test]
fn closed_manifest_is_self_contained_and_binds_each_case_without_using_decision_labels() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("vectors/stream-credit-v1");
    let manifest: Value =
        serde_json::from_slice(&fs::read(root.join("manifest.json")).expect("closed manifest"))
            .expect("manifest is JSON");
    let top = object(&manifest, "manifest");
    exact_keys(
        top,
        &["schema", "profile", "profile_selection", "cases"],
        "manifest",
    );
    assert_eq!(string(top, "schema"), "nbsr-stream-credit-v1-vectors-1");
    let profile = object(value(top, "profile"), "profile");
    exact_keys(profile, &["id", "credit_count", "low_watermark"], "profile");
    assert_eq!(string(profile, "id"), "nbsr-stream-credit-1");
    assert_eq!(number(profile, "credit_count"), 64);
    assert_eq!(number(profile, "low_watermark"), 16);

    let expected_selections = [
        (
            "negotiated",
            true,
            Some("nbsr-stream-credit-1"),
            false,
            Ok(StreamCreditProfile::V1),
            "accept",
        ),
        (
            "unsupported",
            true,
            Some("nbsr-stream-credit-2"),
            false,
            Err(StreamCreditReject::ProfileUnsupported),
            "profile_unsupported",
        ),
        (
            "downgrade",
            true,
            None,
            false,
            Err(StreamCreditReject::Downgrade),
            "downgrade",
        ),
        (
            "forbidden-fallback",
            true,
            None,
            true,
            Err(StreamCreditReject::FallbackForbidden),
            "fallback_forbidden",
        ),
    ];
    let selections = value(top, "profile_selection")
        .as_array()
        .expect("profile_selection array");
    assert_eq!(selections.len(), expected_selections.len());
    for (selection, (id, required, peer, legacy, decision, label)) in
        selections.iter().zip(expected_selections)
    {
        let selection = object(selection, id);
        exact_keys(
            selection,
            &[
                "id",
                "credits_required",
                "peer_profile",
                "explicit_legacy",
                "expected_decision",
            ],
            id,
        );
        assert_eq!(string(selection, "id"), id);
        assert_eq!(boolean(selection, "credits_required"), required);
        assert_eq!(optional_string(selection, "peer_profile"), peer);
        assert_eq!(boolean(selection, "explicit_legacy"), legacy);
        assert_eq!(
            StreamCreditProfile::select(required, peer, legacy),
            decision,
            "{id}"
        );
        assert_eq!(string(selection, "expected_decision"), label, "{id}");
    }

    let expected_cases = [
        (
            "valid-slot-0",
            Ok(StreamCreditPreface {
                channel_id: CHANNEL_ID,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 0,
                quic_stream_id: 4,
            }),
            "accept",
        ),
        (
            "valid-slot-63",
            Ok(StreamCreditPreface {
                channel_id: CHANNEL_ID,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 63,
                quic_stream_id: 4,
            }),
            "accept",
        ),
        (
            "invalid-slot-64",
            Err(StreamCreditReject::InvalidSlot),
            "invalid_slot",
        ),
        (
            "malformed-indefinite",
            Err(StreamCreditReject::MalformedPreface),
            "malformed_preface",
        ),
        (
            "wrong-channel",
            Err(StreamCreditReject::WrongChannel),
            "wrong_channel",
        ),
        (
            "wrong-generation",
            Err(StreamCreditReject::WrongGeneration),
            "wrong_generation",
        ),
        (
            "zero-epoch",
            Err(StreamCreditReject::MalformedPreface),
            "malformed_preface",
        ),
        (
            "wrong-stream",
            Err(StreamCreditReject::WrongStream),
            "wrong_stream",
        ),
        (
            "wrong-session",
            Err(StreamCreditReject::WrongSession),
            "wrong_session",
        ),
    ];
    let cases = value(top, "cases").as_array().expect("cases array");
    assert_eq!(cases.len(), expected_cases.len());
    let mut manifest_paths = std::collections::BTreeSet::new();
    for (case, (id, expected, label)) in cases.iter().zip(expected_cases) {
        let case = object(case, id);
        exact_keys(
            case,
            &[
                "id",
                "preface",
                "preface_hex",
                "sha256",
                "bytes",
                "authenticated_context",
                "expected_decision",
                "slot_mutates",
                "stream_replay_mutates",
                "current_bitmap",
            ],
            id,
        );
        assert_eq!(string(case, "id"), id);
        let relative = string(case, "preface");
        assert!(
            !relative.contains("..") && !relative.starts_with('/'),
            "unsafe vector path"
        );
        manifest_paths.insert(relative.to_owned());
        let wire = fs::read(root.join(relative)).expect("manifest vector file");
        assert_eq!(hex_bytes(string(case, "preface_hex")), wire, "{id}");
        assert_eq!(number(case, "bytes") as usize, wire.len(), "{id}");
        assert_eq!(string(case, "sha256"), sha256_hex(&wire), "{id}");
        assert_eq!(
            decode_stream_credit_preface(&wire, manifest_context(case)),
            expected,
            "{id}"
        );
        assert_eq!(string(case, "expected_decision"), label, "{id}");
        assert_eq!(boolean(case, "slot_mutates"), expected.is_ok(), "{id}");
        assert_eq!(
            boolean(case, "stream_replay_mutates"),
            expected.is_ok(),
            "{id}"
        );
    }
    let mut discovered = Vec::new();
    for entry in fs::read_dir(&root).expect("vector root") {
        let path = entry.expect("vector root entry").path();
        if path.is_dir() {
            discovered.extend(
                fs::read_dir(path)
                    .expect("case directory")
                    .map(|entry| entry.expect("vector file").path()),
            );
        }
    }
    discovered.sort();
    let discovered: std::collections::BTreeSet<_> = discovered
        .iter()
        .map(|path| {
            path.strip_prefix(&root)
                .expect("root-relative vector")
                .to_string_lossy()
                .replace('\\', "/")
        })
        .collect();
    assert_eq!(discovered, manifest_paths, "manifest must be closed");
}

fn object<'a>(value: &'a Value, name: &str) -> &'a Map<String, Value> {
    value.as_object().unwrap_or_else(|| panic!("{name} object"))
}

fn exact_keys(object: &Map<String, Value>, keys: &[&str], name: &str) {
    let actual: std::collections::BTreeSet<_> = object.keys().map(String::as_str).collect();
    let expected: std::collections::BTreeSet<_> = keys.iter().copied().collect();
    assert_eq!(actual, expected, "{name} keys");
}

fn value<'a>(object: &'a Map<String, Value>, key: &str) -> &'a Value {
    object.get(key).unwrap_or_else(|| panic!("{key} field"))
}

fn string<'a>(object: &'a Map<String, Value>, key: &str) -> &'a str {
    value(object, key)
        .as_str()
        .unwrap_or_else(|| panic!("{key} string"))
}

fn optional_string<'a>(object: &'a Map<String, Value>, key: &str) -> Option<&'a str> {
    if value(object, key).is_null() {
        None
    } else {
        Some(string(object, key))
    }
}

fn number(object: &Map<String, Value>, key: &str) -> u64 {
    value(object, key)
        .as_u64()
        .unwrap_or_else(|| panic!("{key} unsigned integer"))
}

fn boolean(object: &Map<String, Value>, key: &str) -> bool {
    value(object, key)
        .as_bool()
        .unwrap_or_else(|| panic!("{key} boolean"))
}

fn manifest_context(case: &Map<String, Value>) -> StreamCreditContext {
    let context = object(
        value(case, "authenticated_context"),
        "authenticated_context",
    );
    exact_keys(
        context,
        &[
            "session_id_hex",
            "authenticated_session_id_hex",
            "channel_id_hex",
            "channel_generation",
            "actual_stream_id",
        ],
        "authenticated_context",
    );
    StreamCreditContext {
        session_id: hex_array(string(context, "session_id_hex")),
        authenticated_session_id: hex_array(string(context, "authenticated_session_id_hex")),
        channel_id: hex_array(string(context, "channel_id_hex")),
        channel_generation: number(context, "channel_generation"),
        quic_stream_id: number(context, "actual_stream_id"),
    }
}

fn hex_array(value: &str) -> [u8; 16] {
    hex_bytes(value).try_into().expect("16-byte hex identity")
}

fn hex_bytes(value: &str) -> Vec<u8> {
    assert_eq!(value.len() % 2, 0, "even hex length");
    (0..value.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&value[index..index + 2], 16).expect("lowercase hex"))
        .collect()
}
