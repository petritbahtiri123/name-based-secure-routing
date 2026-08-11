use std::fs;
use std::path::PathBuf;

use nbsr_transport::{
    StreamCreditContext, StreamCreditPreface, StreamCreditProfile, StreamCreditReject,
    decode_stream_credit_preface, encode_stream_credit_preface,
};
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
fn closed_manifest_hashes_all_preface_vectors_without_using_decision_labels() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("vectors/stream-credit-v1");
    let cases = [
        (
            "valid/slot-0.cbor",
            30,
            "ea0a2fa1c06ce701e54073d59fb7161af31006b35dc46b8182617dd0e9880bfa",
        ),
        (
            "valid/slot-63.cbor",
            31,
            "76a0aba417236828cf39b0e3f186ff93c5df03ca06b0da23eb4ee527b33bb3b3",
        ),
        (
            "invalid/slot-64.cbor",
            31,
            "3aa7e888be1f9cd155330b3718e52164d74100c93eb75f1cd97e32a463e1a7cd",
        ),
        (
            "invalid/malformed-indefinite.cbor",
            2,
            "636407da9d7e69e4f4cc4f4d678c2223c658ce6de4f7f0156975024d469a9c02",
        ),
        (
            "invalid/wrong-channel.cbor",
            30,
            "40e75d125343fe1e2d05ce64a5623ed7a77fa8e44695287827ebc74428d72d21",
        ),
        (
            "invalid/wrong-generation.cbor",
            30,
            "12c69ceff47a2936a1e4681b87028fb84fcc569d9617b8c1e5ed4984246ab280",
        ),
        (
            "invalid/zero-epoch.cbor",
            30,
            "35e3ee4e9d4c0c7dff9fdf926f9f605a88da97d7c82d2b4a1685fdf742bad202",
        ),
        (
            "invalid/wrong-stream.cbor",
            30,
            "1916c436bab4dc3d34d8c3d63e70a8b3e648ea2dca36d691d5e35dc0659368e0",
        ),
    ];
    let manifest = fs::read_to_string(root.join("manifest.json")).expect("closed manifest");
    for (relative, bytes, expected_hash) in cases {
        let wire = vector(relative);
        assert_eq!(wire.len(), bytes, "{relative}");
        assert_eq!(sha256_hex(&wire), expected_hash, "{relative}");
        assert!(manifest.contains(relative), "manifest omits {relative}");
        assert!(
            manifest.contains(expected_hash),
            "manifest hash differs for {relative}"
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
    assert_eq!(discovered.len(), cases.len(), "manifest must be closed");
}
