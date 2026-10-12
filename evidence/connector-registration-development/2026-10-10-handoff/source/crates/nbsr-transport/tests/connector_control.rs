#[path = "../src/connector_control.rs"]
mod codec;
use sha2::{Digest, Sha256};
#[test]
fn retained_development_vectors() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../vectors/connector-registration-development-v1");
    let manifest: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("manifest.json")).unwrap()).unwrap();
    for case in manifest["cases"].as_array().unwrap() {
        let name = case["file"].as_str().unwrap();
        let raw = std::fs::read(root.join(name)).unwrap();
        assert_eq!(
            Sha256::digest(&raw)
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect::<String>(),
            manifest["artifacts"][name]["sha256"].as_str().unwrap()
        );
        let result = codec::decode(case["alpn"].as_str().unwrap(), &raw);
        assert_eq!(
            result.is_ok(),
            case["accepted"].as_bool().unwrap(),
            "{name}: {result:?}"
        );
        if let Ok(v) = result {
            assert_eq!(codec::encode(&v), raw);
        }
    }
}
