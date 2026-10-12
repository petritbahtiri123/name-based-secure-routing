//! In-memory development owner only. No library export, sockets or trust producer.
#![cfg(test)]
use crate::cleanup::CleanupTicket;
use crate::codec::{self, Result, Value as V, bytes, get, map, uint};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, VecDeque};
fn hash(v: &V) -> [u8; 32] {
    Sha256::digest(codec::encode(v)).into()
}
fn obj(items: Vec<(u64, V)>) -> V {
    V::Map(items.into_iter().collect())
}
fn same(a: &[u8; 32], b: &[u8; 32]) -> bool {
    let mut x = 0u8;
    for i in 0..32 {
        x |= std::hint::black_box(a[i] ^ b[i]);
    }
    std::hint::black_box(x) == 0
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Binding {
    pub profile: String,
    pub action: u64,
    pub connection: u64,
    pub session: [u8; 16],
    pub peer: [u8; 32],
    pub service: [u8; 32],
    pub gateway: String,
    pub operator: [u8; 32],
    pub digest: [u8; 32],
    pub dependencies: [u8; 32],
    pub policy: [u8; 32],
}
// Synthetic receipts are possible only in this test-compiled module. A future
// runtime must provide a sealed verified-authority implementation, not this API.
#[derive(Clone)]
pub struct Decision {
    pub binding: Binding,
    pub revision: u64,
    pub expires: u64,
}
pub trait Authority {
    fn verify(&mut self, binding: &Binding, request: &V, now: u64) -> Result<Decision>;
    fn revision(&self) -> u64;
}
pub trait Transport {
    fn protocol(&self) -> &str;
    fn export(&mut self, label: &str, context: &[u8]) -> Result<[u8; 32]>;
    fn nonce(&mut self) -> Result<[u8; 32]>;
    fn close(&mut self, connection: u64) -> Result<()>;
}
#[derive(Clone)]
struct Operation {
    counter: u64,
    request: V,
    binding: Binding,
    decision: Decision,
    challenge: V,
    deadline: u64,
    proof: Option<V>,
    result: Option<V>,
}
struct Connection {
    cleanup: Option<CleanupTicket>,
    terminal: bool,
    session: [u8; 16],
    peer: [u8; 32],
    rx: u64,
    tx: u64,
    high: u64,
    attempt_deadline: u64,
    pending: Option<Operation>,
    completed: VecDeque<Operation>,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Owner {
    pub binding: Binding,
    pub registration: [u8; 16],
    pub generation: u64,
    pub expires: u64,
    pub digest: [u8; 32],
    pub eligible: bool,
}
pub struct Gateway {
    service: [u8; 32],
    gateway: String,
    operator: [u8; 32],
    peer: [u8; 32],
    epoch: [u8; 16],
    generation: u64,
    pin: BTreeMap<u64, V>,
    skew: u64,
    pub owner: Option<Owner>,
    connections: BTreeMap<u64, Connection>,
    last_time: Option<u64>,
    clock_failed: bool,
}
#[derive(Clone, Copy)]
pub enum Invalidation {
    DenyNew,
    Terminate,
}
impl Gateway {
    pub fn new(policy: V, epoch: [u8; 16], skew: u64) -> Result<Self> {
        codec::validate_body(24576, &policy)?;
        if epoch == [0; 16] || skew > 253402300799 {
            return Err("invalid explicit policy");
        }
        let pin = map(&policy)?.clone();
        Ok(Self {
            service: bytes(get(&pin, 3)?, 32, false)?.try_into().unwrap(),
            gateway: if let V::Text(s) = get(&pin, 6)? {
                s.clone()
            } else {
                return Err("gateway");
            },
            operator: bytes(get(&pin, 4)?, 32, false)?.try_into().unwrap(),
            peer: bytes(get(&pin, 8)?, 32, false)?.try_into().unwrap(),
            epoch,
            generation: 0,
            pin,
            skew,
            owner: None,
            connections: BTreeMap::new(),
            last_time: None,
            clock_failed: false,
        })
    }
    // Explicit fixture time is shared by this serialized gateway. Invalid time
    // withdraws admission, but never releases resources or confirms cleanup.
    fn observe_time(&mut self, now: u64) -> Result<()> {
        if self.clock_failed
            || now > 253402300799
            || self.last_time.is_some_and(|previous| now < previous)
        {
            self.clock_failed = true;
            if let Some(owner) = &mut self.owner {
                owner.eligible = false;
            }
            for connection in self.connections.values_mut() {
                connection.terminal = true;
            }
            return Err("invalid or rolled-back fixture clock; cleanup required");
        }
        self.last_time = Some(now);
        Ok(())
    }
    pub fn attach(&mut self, id: u64, session: [u8; 16], peer: [u8; 32], now: u64) -> Result<()> {
        self.observe_time(now)?;
        if id == 0
            || session == [0; 16]
            || peer != self.peer
            || self.connections.contains_key(&id)
            || self.connections.len() >= 2
        {
            return Err("connection admission");
        }
        self.connections.insert(
            id,
            Connection {
                cleanup: None,
                terminal: false,
                session,
                peer,
                rx: 0,
                tx: 0,
                high: 0,
                attempt_deadline: now.saturating_add(5).min(253402300799),
                pending: None,
                completed: VecDeque::new(),
            },
        );
        Ok(())
    }
    pub fn cache_size(&self, id: u64) -> usize {
        self.connections.get(&id).map_or(0, |c| c.completed.len())
    }
    pub fn handle(
        &mut self,
        id: u64,
        raw: &[u8],
        now: u64,
        authority: Option<&mut dyn Authority>,
        transport: &mut dyn Transport,
    ) -> Result<Option<Vec<u8>>> {
        self.observe_time(now)?;
        let envelope = codec::decode(transport.protocol(), raw)?;
        let mut c = self.connections.remove(&id).ok_or("unknown connection")?;
        let result = self.process(id, &mut c, envelope, now, authority, transport);
        if !matches!(result, Ok(None)) {
            self.connections.insert(id, c);
        }
        result
    }
    fn process(
        &mut self,
        id: u64,
        c: &mut Connection,
        e: V,
        now: u64,
        authority: Option<&mut dyn Authority>,
        t: &mut dyn Transport,
    ) -> Result<Option<Vec<u8>>> {
        let m = map(&e)?;
        if c.terminal
            || (self
                .owner
                .as_ref()
                .is_none_or(|o| o.binding.connection != id)
                && now >= c.attempt_deadline)
        {
            return Err("attempt ended; cleanup required");
        }
        if bytes(get(m, 3)?, 16, true)? != c.session
            || uint(get(m, 4)?)? <= c.rx
            || c.tx == u64::MAX
        {
            return Err("session/sequence");
        }
        c.rx = uint(get(m, 4)?)?;
        let rid = bytes(get(m, 2)?, 16, true)?.to_vec();
        let counter = u64::from_be_bytes(rid[8..].try_into().unwrap());
        let kind = uint(get(m, 1)?)?;
        let body = get(m, 5)?.clone();
        if let Some(o) = &mut self.owner
            && now >= o.expires
        {
            o.eligible = false;
        }
        if c.pending.as_ref().is_some_and(|p| now >= p.deadline) {
            c.pending = None;
        }
        match kind {
            24576 => {
                if let Some(p) = &c.pending {
                    if p.counter == counter {
                        if p.request != body {
                            return Err("changed retry");
                        };
                        return Self::response(c, &rid, 24577, p.challenge.clone()).map(Some);
                    }
                    return Err("pending capacity");
                }
                if let Some(p) = c.completed.iter().find(|p| p.counter == counter) {
                    if p.request != body {
                        return Err("changed retry");
                    };
                    let result = p.result.clone().ok_or("failed result")?;
                    let current = self.owner.as_ref().is_some_and(|o| {
                        o.binding.connection == id
                            && o.eligible
                            && o.digest == Self::accept_digest(&c.session, &rid, &result)
                    });
                    if !current {
                        return Err("stale retry");
                    };
                    return Self::response(c, &rid, 24579, result).map(Some);
                }
                if c.high.checked_add(1) != Some(counter) {
                    return Err("counter replay");
                };
                c.high = counter;
                let b = map(&body)?;
                if uint(get(b, 14)?)?.abs_diff(now) > self.skew {
                    return Err("request freshness");
                }
                for k in [2, 3, 4, 5, 6, 7, 8, 12] {
                    if get(b, k)? != get(&self.pin, k)? {
                        return Err("principal policy pin");
                    }
                }
                let binding = Binding {
                    profile: "connector-registration-development-v1".into(),
                    action: 24576,
                    connection: id,
                    session: c.session,
                    peer: c.peer,
                    service: bytes(get(b, 3)?, 32, false)?.try_into().unwrap(),
                    gateway: match get(b, 6)? {
                        V::Text(s) => s.clone(),
                        _ => return Err("gateway"),
                    },
                    operator: bytes(get(b, 4)?, 32, false)?.try_into().unwrap(),
                    digest: hash(&body),
                    dependencies: bytes(get(b, 11)?, 32, false)?.try_into().unwrap(),
                    policy: bytes(get(b, 12)?, 32, false)?.try_into().unwrap(),
                };
                if binding.service != self.service
                    || binding.gateway != self.gateway
                    || binding.operator != self.operator
                    || bytes(get(b, 8)?, 32, false)? != self.peer
                {
                    return Err("principal/scope");
                }
                self.check_owner(id, &body, now)?;
                let a = authority.ok_or("missing verified authority")?;
                let decision = a.verify(&binding, &body, now)?;
                if decision.binding != binding
                    || decision.expires <= now
                    || decision.expires > 253402300799
                    || decision.revision != a.revision()
                {
                    return Err("invalid authority");
                }
                let nonce = t.nonce()?;
                if nonce == [0; 32] {
                    return Err("nonce");
                };
                let deadline = now
                    .checked_add(5)
                    .ok_or("deadline overflow")?
                    .min(decision.expires)
                    .min(253402300799);
                let challenge = obj(vec![
                    (0, V::Uint(1)),
                    (1, V::Bytes(binding.digest.to_vec())),
                    (2, V::Bytes(nonce.to_vec())),
                    (3, V::Uint(deadline)),
                ]);
                c.pending = Some(Operation {
                    counter,
                    request: body,
                    binding,
                    decision,
                    challenge: challenge.clone(),
                    deadline,
                    proof: None,
                    result: None,
                });
                Self::response(c, &rid, 24577, challenge).map(Some)
            }
            24578 => {
                if let Some(p) = c.completed.iter().find(|p| p.counter == counter) {
                    if p.proof.as_ref() != Some(&body) {
                        return Err("changed proof");
                    };
                    let result = p.result.clone().ok_or("result")?;
                    if !self.owner.as_ref().is_some_and(|o| {
                        o.binding.connection == id
                            && o.eligible
                            && o.digest == Self::accept_digest(&c.session, &rid, &result)
                    }) {
                        return Err("stale proof");
                    };
                    return Self::response(c, &rid, 24579, result).map(Some);
                }
                if c.pending.as_ref().is_none_or(|p| p.counter != counter) {
                    return Err("unrelated proof");
                }
                let mut p = c.pending.take().ok_or("no pending operation")?;
                if p.counter != counter || now >= p.deadline {
                    return Err("proof correlation/deadline");
                }
                let b = map(&body)?;
                let challenge = map(&p.challenge)?;
                if get(b, 1)? != get(challenge, 1)? || get(b, 2)? != get(challenge, 2)? {
                    return Err("proof correlation");
                }
                let request = map(&p.request)?;
                let context = codec::encode(&V::Array(vec![
                    V::Text("NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1".into()),
                    V::Uint(1),
                    V::Bytes(c.session.to_vec()),
                    V::Bytes(rid.clone()),
                    get(challenge, 1)?.clone(),
                    get(challenge, 2)?.clone(),
                    get(request, 4)?.clone(),
                    get(request, 5)?.clone(),
                    get(request, 6)?.clone(),
                    get(request, 8)?.clone(),
                    get(request, 12)?.clone(),
                ]));
                let expected = t.export("EXPORTER-NBSR-Connector-Registration-v1", &context)?;
                let received: [u8; 32] = bytes(get(b, 3)?, 32, false)?.try_into().unwrap();
                if !same(&expected, &received) {
                    return Err("proof binding");
                }
                let a = authority.ok_or("missing authority")?;
                let decision = a.verify(&p.binding, &p.request, now)?;
                if decision.binding != p.binding
                    || decision.revision != p.decision.revision
                    || decision.revision != a.revision()
                    || decision.expires <= now
                    || decision.expires > 253402300799
                {
                    return Err("authority changed");
                }
                self.check_owner(id, &p.request, now)?;
                let lease = uint(get(request, 13)?)?;
                let expires = now
                    .checked_add(lease)
                    .ok_or("expiry overflow")?
                    .min(decision.expires)
                    .min(253402300799);
                if expires <= now {
                    return Err("expiry");
                }
                let (registration, generation) = if let Some(o) = &self.owner {
                    (o.registration, o.generation)
                } else {
                    let nonce = t.nonce()?;
                    let registration = nonce[..16].try_into().unwrap();
                    if registration == [0; 16] {
                        return Err("registration id");
                    };
                    let generation = self
                        .generation
                        .checked_add(1)
                        .ok_or("generation exhausted")?;
                    (registration, generation)
                };
                // Revision check after injected calls and immediately before ownership mutation.
                if decision.revision != a.revision() {
                    return Err("revision changed before commit");
                }
                let accepted = obj(vec![
                    (0, V::Uint(1)),
                    (1, V::Bytes(p.binding.digest.to_vec())),
                    (2, V::Bytes(registration.to_vec())),
                    (3, V::Bytes(self.epoch.to_vec())),
                    (4, V::Uint(generation)),
                    (5, V::Uint(now)),
                    (6, V::Uint(expires)),
                    (7, V::Uint(now + (expires - now) / 2)),
                    (8, V::Bytes(p.binding.dependencies.to_vec())),
                    (9, V::Bytes(p.binding.policy.to_vec())),
                ]);
                codec::validate_body(24579, &accepted)?;
                let digest = Self::accept_digest(&c.session, &rid, &accepted);
                self.generation = generation;
                self.owner = Some(Owner {
                    binding: p.binding.clone(),
                    registration,
                    generation,
                    expires,
                    digest,
                    eligible: true,
                });
                p.proof = Some(body);
                p.result = Some(accepted.clone());
                c.completed.push_back(p);
                while c.completed.len() > 4 {
                    c.completed.pop_front();
                }
                Self::response(c, &rid, 24579, accepted).map(Some)
            }
            24581 => {
                let b = map(&body)?;
                let owner = self.owner.as_mut().ok_or("no owner")?;
                if owner.binding.connection != id
                    || bytes(get(b, 1)?, 16, true)? != owner.registration
                    || bytes(get(b, 2)?, 16, true)? != self.epoch
                    || uint(get(b, 3)?)? != owner.generation
                    || bytes(get(b, 4)?, 32, false)? != owner.digest
                {
                    return Err("withdraw ownership");
                }
                owner.eligible = false;
                c.pending = None;
                t.close(id)?;
                self.owner = None;
                Ok(None)
            }
            _ => Err("unexpected message direction"),
        }
    }
    fn check_owner(&self, id: u64, request: &V, now: u64) -> Result<()> {
        let b = map(request)?;
        if get(b, 1)? == &V::Text("register".into()) {
            if self.owner.is_some() {
                return Err("duplicate owner");
            }
        } else {
            let o = self.owner.as_ref().ok_or("no owner")?;
            if o.binding.connection != id
                || !o.eligible
                || now >= o.expires
                || bytes(get(b, 15)?, 32, false)? != o.digest
            {
                return Err("renew ownership");
            }
        }
        Ok(())
    }
    fn response(c: &mut Connection, rid: &[u8], kind: u64, body: V) -> Result<Vec<u8>> {
        c.tx = c.tx.checked_add(1).ok_or("tx exhausted")?;
        let v = obj(vec![
            (0, V::Uint(1)),
            (1, V::Uint(kind)),
            (2, V::Bytes(rid.to_vec())),
            (3, V::Bytes(c.session.to_vec())),
            (4, V::Uint(c.tx)),
            (5, body),
        ]);
        let raw = codec::encode(&v);
        codec::decode(codec::ALPN, &raw)?;
        Ok(raw)
    }
    pub fn accept_digest(session: &[u8; 16], rid: &[u8], body: &V) -> [u8; 32] {
        hash(&V::Array(vec![
            V::Text("NBSR-CONNECTOR-ACCEPT-DIGEST-v1".into()),
            V::Uint(1),
            V::Bytes(session.to_vec()),
            V::Bytes(rid.to_vec()),
            body.clone(),
        ]))
    }
    pub fn invalidate(
        &mut self,
        dependency: [u8; 32],
        mode: Invalidation,
        t: &mut dyn Transport,
    ) -> Result<()> {
        for c in self.connections.values_mut() {
            if c.pending
                .as_ref()
                .is_some_and(|p| p.binding.dependencies == dependency)
            {
                c.pending = None;
            }
        }
        if let Some(o) = &mut self.owner
            && o.binding.dependencies == dependency
        {
            o.eligible = false;
            if matches!(mode, Invalidation::Terminate) {
                let id = o.binding.connection;
                self.close_attempt(id, t)?;
            }
        }
        Ok(())
    }
    pub fn close_attempt(&mut self, id: u64, t: &mut dyn Transport) -> Result<()> {
        let c = self.connections.get_mut(&id).ok_or("unknown attempt")?;
        c.terminal = true;
        c.pending = None;
        if let Some(o) = &mut self.owner
            && o.binding.connection == id
        {
            o.eligible = false;
        }
        if c.cleanup.is_some() {
            return Err("asynchronous cleanup requires exact confirmation");
        }
        t.close(id)?;
        self.connections.remove(&id);
        if self
            .owner
            .as_ref()
            .is_some_and(|o| o.binding.connection == id)
        {
            self.owner = None;
        }
        Ok(())
    }
    pub fn begin_cleanup(&mut self, id: u64) -> Result<CleanupTicket> {
        let c = self.connections.get_mut(&id).ok_or("unknown connection")?;
        c.terminal = true;
        c.pending = None;
        if let Some(o) = self.owner.as_mut().filter(|o| o.binding.connection == id) {
            o.eligible = false;
        }
        if let Some(ticket) = &c.cleanup {
            return Ok(ticket.clone());
        }
        let owner = self
            .owner
            .as_ref()
            .filter(|o| o.binding.connection == id)
            .cloned();
        let ticket = CleanupTicket::new(id, c.session, owner);
        c.cleanup = Some(ticket.clone());
        Ok(ticket)
    }
    fn matches_cleanup(&self, ticket: &CleanupTicket) -> bool {
        self.connections.get(&ticket.connection).is_some_and(|c| {
            c.session == ticket.session
                && c.cleanup
                    .as_ref()
                    .is_some_and(|current| current.same_attempt(ticket))
        }) && self
            .owner
            .as_ref()
            .filter(|o| o.binding.connection == ticket.connection)
            == ticket.owner.as_ref()
    }
    pub fn retry_cleanup(&mut self, ticket: &CleanupTicket) -> Result<CleanupTicket> {
        if !self.matches_cleanup(ticket) || !matches!(ticket.outcome(), Some(Err(_))) {
            return Err("cleanup is not a current failed attempt");
        }
        let next = CleanupTicket::new(ticket.connection, ticket.session, ticket.owner.clone());
        self.connections
            .get_mut(&ticket.connection)
            .ok_or("unknown connection")?
            .cleanup = Some(next.clone());
        Ok(next)
    }
    pub fn finish_cleanup(&mut self, ticket: &CleanupTicket) -> Result<()> {
        if !self.matches_cleanup(ticket) {
            return Err("stale cleanup owner/attempt");
        }
        ticket.outcome().ok_or("cleanup pending")??;
        self.connections.remove(&ticket.connection);
        if ticket.owner.is_some() {
            self.owner = None;
        }
        Ok(())
    }
    pub fn poll(&mut self, now: u64, t: &mut dyn Transport) -> Result<()> {
        self.observe_time(now)?;
        let mut due = Vec::new();
        for (id, c) in &mut self.connections {
            if c.pending.as_ref().is_some_and(|p| now >= p.deadline) {
                c.pending = None;
            }
            let owned = self.owner.as_ref().filter(|o| o.binding.connection == *id);
            if owned.is_some_and(|o| now >= o.expires)
                || (owned.is_none() && now >= c.attempt_deadline)
            {
                due.push(*id);
            }
        }
        let mut failed = false;
        for id in due {
            if self.close_attempt(id, t).is_err() {
                failed = true;
            }
        }
        if failed {
            Err("cleanup failed; ownership retained")
        } else {
            Ok(())
        }
    }
}
