#[path = "../src/connector_control.rs"]
mod codec;
#[path = "../src/connector_registration.rs"]
mod owner;
use codec::{Value as V, bytes, get, map};
use owner::{Authority, Binding, Decision, Gateway, Invalidation, Transport};
use sha2::{Digest, Sha256};
struct FixtureAuthority {
    revision: u64,
    expiry: u64,
    deny: bool,
    wrong: bool,
    flip: bool,
    calls: u64,
}
impl Default for FixtureAuthority {
    fn default() -> Self {
        Self {
            revision: 1,
            expiry: 1000,
            deny: false,
            wrong: false,
            flip: false,
            calls: 0,
        }
    }
}
impl Authority for FixtureAuthority {
    fn verify(&mut self, b: &Binding, _: u64) -> codec::Result<Decision> {
        self.calls += 1;
        if self.deny {
            return Err("explicit fixture rejection");
        };
        let mut binding = b.clone();
        if self.wrong {
            binding.service = [0; 32]
        };
        let revision = self.revision;
        if self.flip && self.calls == 2 {
            self.revision += 1
        };
        Ok(Decision {
            binding,
            revision,
            expires: self.expiry,
        })
    }
    fn revision(&self) -> u64 {
        self.revision
    }
}
#[derive(Default)]
struct FixtureTransport {
    fail_close: bool,
    closed: Vec<u64>,
    bad_export: bool,
}
impl Transport for FixtureTransport {
    fn export(&mut self, label: &str, context: &[u8]) -> codec::Result<[u8; 32]> {
        assert_eq!(label, "EXPORTER-NBSR-Connector-Registration-v1");
        if self.bad_export {
            return Ok([0; 32]);
        };
        let mut h = Sha256::new();
        h.update(b"EXPLICIT NON-TLS TEST FIXTURE");
        h.update(label);
        h.update(context);
        Ok(h.finalize().into())
    }
    fn nonce(&mut self) -> codec::Result<[u8; 32]> {
        Ok([0x63; 32])
    }
    fn close(&mut self, id: u64) -> codec::Result<()> {
        if self.fail_close {
            return Err("fixture close failed");
        };
        self.closed.push(id);
        Ok(())
    }
}
fn request() -> V {
    let raw = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/connector-registration-development-v1/request.cbor"),
    )
    .unwrap();
    get(map(&codec::decode(codec::ALPN, &raw).unwrap()).unwrap(), 5)
        .unwrap()
        .clone()
}
fn env(body: V, kind: u64, counter: u64, seq: u64) -> Vec<u8> {
    let mut rid = b"ssssssss".to_vec();
    rid.extend(counter.to_be_bytes());
    codec::encode(&V::Map(
        [
            (0, V::Uint(1)),
            (1, V::Uint(kind)),
            (2, V::Bytes(rid)),
            (3, V::Bytes(vec![b's'; 16])),
            (4, V::Uint(seq)),
            (5, body),
        ]
        .into_iter()
        .collect(),
    ))
}
fn setup() -> (Gateway, FixtureAuthority, FixtureTransport) {
    let request = request();
    let b = map(&request).unwrap();
    let mut g = Gateway::new(request.clone(), [8; 16], 0).unwrap();
    g.attach(
        1,
        [b's'; 16],
        bytes(get(b, 8).unwrap(), 32, false)
            .unwrap()
            .try_into()
            .unwrap(),
        100,
    )
    .unwrap();
    (g, FixtureAuthority::default(), FixtureTransport::default())
}
fn complete(
    g: &mut Gateway,
    a: &mut FixtureAuthority,
    t: &mut FixtureTransport,
    mut body: V,
    counter: u64,
    now: u64,
) -> V {
    if let V::Map(b) = &mut body {
        b.insert(14, V::Uint(now));
    }
    let challenge = g
        .handle(
            1,
            &env(body.clone(), 24576, counter, counter * 2 - 1),
            now,
            Some(a),
            t,
        )
        .unwrap()
        .unwrap();
    let challenge = codec::decode(codec::ALPN, &challenge).unwrap();
    let cm = map(get(map(&challenge).unwrap(), 5).unwrap()).unwrap();
    let req = map(&body).unwrap();
    let mut rid = b"ssssssss".to_vec();
    rid.extend(counter.to_be_bytes());
    let context = codec::encode(&V::Array(vec![
        V::Text("NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1".into()),
        V::Uint(1),
        V::Bytes(vec![b's'; 16]),
        V::Bytes(rid),
        get(cm, 1).unwrap().clone(),
        get(cm, 2).unwrap().clone(),
        get(req, 4).unwrap().clone(),
        get(req, 5).unwrap().clone(),
        get(req, 6).unwrap().clone(),
        get(req, 8).unwrap().clone(),
        get(req, 12).unwrap().clone(),
    ]));
    let proof = V::Map(
        [
            (0, V::Uint(1)),
            (1, get(cm, 1).unwrap().clone()),
            (2, get(cm, 2).unwrap().clone()),
            (
                3,
                V::Bytes(
                    t.export("EXPORTER-NBSR-Connector-Registration-v1", &context)
                        .unwrap()
                        .to_vec(),
                ),
            ),
        ]
        .into_iter()
        .collect(),
    );
    let result = g
        .handle(1, &env(proof, 24578, counter, counter * 2), now, Some(a), t)
        .unwrap()
        .unwrap();
    get(
        map(&codec::decode(codec::ALPN, &result).unwrap()).unwrap(),
        5,
    )
    .unwrap()
    .clone()
}
#[test]
fn register_renew_cache_eviction_withdraw() {
    let (mut g, mut a, mut t) = setup();
    let mut result = complete(&mut g, &mut a, &mut t, request(), 1, 100);
    let initial = g.owner.clone().unwrap();
    for counter in 2..=10 {
        let mut b = map(&request()).unwrap().clone();
        b.insert(1, V::Text("renew".into()));
        b.insert(15, V::Bytes(g.owner.as_ref().unwrap().digest.to_vec()));
        result = complete(&mut g, &mut a, &mut t, V::Map(b), counter, 100 + counter);
        assert_eq!(g.owner.as_ref().unwrap().generation, initial.generation);
        assert_eq!(g.owner.as_ref().unwrap().registration, initial.registration);
        assert!(g.cache_size(1) <= 4)
    }
    assert_eq!(g.cache_size(1), 4);
    let calls = a.calls;
    assert!(
        g.handle(1, &env(request(), 24576, 1, 21), 111, Some(&mut a), &mut t)
            .is_err()
    );
    assert_eq!(a.calls, calls);
    let o = g.owner.clone().unwrap();
    let accept = map(&result).unwrap();
    let wd = V::Map(
        [
            (0, V::Uint(1)),
            (1, get(accept, 2).unwrap().clone()),
            (2, get(accept, 3).unwrap().clone()),
            (3, V::Uint(o.generation)),
            (4, V::Bytes(o.digest.to_vec())),
        ]
        .into_iter()
        .collect(),
    );
    t.fail_close = true;
    assert!(
        g.handle(1, &env(wd.clone(), 24581, 11, 22), 111, None, &mut t)
            .is_err()
    );
    assert!(g.owner.is_some());
    assert!(!g.owner.as_ref().unwrap().eligible);
    t.fail_close = false;
    assert_eq!(
        g.handle(1, &env(wd, 24581, 11, 23), 111, None, &mut t),
        Ok(None)
    );
    assert!(g.owner.is_none());
    assert_eq!(t.closed, vec![1]);
}
#[test]
fn authority_scope_and_replay_rejections() {
    for fault in 0..6 {
        let (mut g, mut a, mut t) = setup();
        let mut b = map(&request()).unwrap().clone();
        match fault {
            0 => a.deny = true,
            1 => a.wrong = true,
            2 => a.expiry = 100,
            3 => {
                b.insert(3, V::Bytes(vec![99; 32]));
            }
            4 => {
                b.insert(8, V::Bytes(vec![99; 32]));
            }
            _ => {}
        }
        let result = if fault == 5 {
            g.handle(1, &env(V::Map(b), 24576, 1, 1), 100, None, &mut t)
        } else {
            g.handle(1, &env(V::Map(b), 24576, 1, 1), 100, Some(&mut a), &mut t)
        };
        assert!(result.is_err(), "fault {fault}");
        assert!(g.owner.is_none())
    }
}
#[test]
fn exact_pending_retry_and_changed_body() {
    let (mut g, mut a, mut t) = setup();
    let first = g
        .handle(1, &env(request(), 24576, 1, 1), 100, Some(&mut a), &mut t)
        .unwrap()
        .unwrap();
    let retry = g
        .handle(1, &env(request(), 24576, 1, 2), 101, Some(&mut a), &mut t)
        .unwrap()
        .unwrap();
    assert_eq!(
        get(
            map(&codec::decode(codec::ALPN, &first).unwrap()).unwrap(),
            5
        ),
        get(
            map(&codec::decode(codec::ALPN, &retry).unwrap()).unwrap(),
            5
        )
    );
    assert_eq!(a.calls, 1);
    let mut b = map(&request()).unwrap().clone();
    b.insert(13, V::Uint(59));
    assert!(
        g.handle(1, &env(V::Map(b), 24576, 1, 3), 101, Some(&mut a), &mut t)
            .is_err()
    );
    assert!(g.owner.is_none());
}
#[test]
fn duplicate_owner_revocation_and_expiry() {
    let (mut g, mut a, mut t) = setup();
    complete(&mut g, &mut a, &mut t, request(), 1, 100);
    let o = g.owner.clone().unwrap();
    g.attach(2, [b's'; 16], o.binding.peer, 100).unwrap();
    assert!(
        g.handle(2, &env(request(), 24576, 1, 1), 101, Some(&mut a), &mut t)
            .is_err()
    );
    assert_eq!(g.owner, Some(o.clone()));
    g.invalidate(o.binding.dependencies, Invalidation::DenyNew, &mut t)
        .unwrap();
    assert!(!g.owner.as_ref().unwrap().eligible);
    assert!(
        g.handle(1, &env(request(), 24576, 1, 3), 101, Some(&mut a), &mut t)
            .is_err()
    );
    t.fail_close = true;
    assert!(
        g.invalidate(o.binding.dependencies, Invalidation::Terminate, &mut t)
            .is_err()
    );
    assert!(g.owner.is_some());
    t.fail_close = false;
    g.invalidate(o.binding.dependencies, Invalidation::Terminate, &mut t)
        .unwrap();
    assert!(g.owner.is_none());
    let (mut g, mut a, mut t) = setup();
    complete(&mut g, &mut a, &mut t, request(), 1, 100);
    assert!(
        g.handle(1, &env(request(), 24576, 1, 3), 160, Some(&mut a), &mut t)
            .is_err()
    );
    assert!(!g.owner.as_ref().unwrap().eligible);
}
#[test]
fn complete_principal_pin_rejects_changed_request_fields() {
    for key in [2, 5, 7, 12] {
        let (mut g, mut a, mut t) = setup();
        let mut b = map(&request()).unwrap().clone();
        b.insert(
            key,
            match key {
                2 => V::Text("other.connector".into()),
                7 => V::Bytes(b"other-key".to_vec()),
                _ => V::Bytes(vec![99; 32]),
            },
        );
        assert!(
            g.handle(1, &env(V::Map(b), 24576, 1, 1), 100, Some(&mut a), &mut t)
                .is_err(),
            "pin key {key}"
        );
    }
}
#[test]
fn confirmed_cleanup_releases_connection_slot() {
    let (mut g, mut a, mut t) = setup();
    complete(&mut g, &mut a, &mut t, request(), 1, 100);
    let o = g.owner.clone().unwrap();
    g.attach(2, [b'x'; 16], o.binding.peer, 100).unwrap();
    g.invalidate(o.binding.dependencies, Invalidation::Terminate, &mut t)
        .unwrap();
    assert!(g.attach(3, [b'y'; 16], o.binding.peer, 100).is_ok());
}
