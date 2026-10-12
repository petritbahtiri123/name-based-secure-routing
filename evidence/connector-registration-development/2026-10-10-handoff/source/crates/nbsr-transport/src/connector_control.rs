//! Development-test-only connector codec. Not exported by the transport library.
#![cfg(test)]
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
pub const ALPN: &str = "nbsr-connector-dev-1";
pub const REQUEST: u64 = 24576;
pub const WITHDRAW: u64 = 24581;
pub type Result<T> = std::result::Result<T, &'static str>;
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Value {
    Uint(u64),
    Bytes(Vec<u8>),
    Text(String),
    Array(Vec<Value>),
    Map(BTreeMap<u64, Value>),
    Bool(bool),
    Null,
}
macro_rules! require {
    ($e:expr) => {
        if !$e {
            return Err("connector development input rejected");
        }
    };
}
pub fn uint(v: &Value) -> Result<u64> {
    if let Value::Uint(n) = v {
        Ok(*n)
    } else {
        Err("expected uint")
    }
}
pub fn bytes(v: &Value, n: usize, nonzero: bool) -> Result<&[u8]> {
    if let Value::Bytes(b) = v {
        require!(b.len() == n && (!nonzero || b.iter().any(|x| *x != 0)));
        Ok(b)
    } else {
        Err("expected bytes")
    }
}
pub fn map(v: &Value) -> Result<&BTreeMap<u64, Value>> {
    if let Value::Map(m) = v {
        Ok(m)
    } else {
        Err("expected map")
    }
}
pub fn get(m: &BTreeMap<u64, Value>, k: u64) -> Result<&Value> {
    m.get(&k).ok_or("missing field")
}
fn exact(m: &BTreeMap<u64, Value>, n: usize) -> Result<()> {
    require!(m.len() == n && (0..n as u64).all(|k| m.contains_key(&k)));
    Ok(())
}
fn bounded(v: &Value, lo: u64, hi: u64) -> Result<u64> {
    let n = uint(v)?;
    require!(n >= lo && n <= hi);
    Ok(n)
}
fn text_id(v: &Value) -> Result<()> {
    let Value::Text(s) = v else {
        return Err("expected text");
    };
    let b = s.as_bytes();
    require!(!b.is_empty() && b.len() <= 64 && b[0].is_ascii_lowercase());
    let mut separator = false;
    for c in b {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            separator = false
        } else {
            require!(!separator && matches!(c, b'.' | b'_' | b'-'));
            separator = true
        }
    }
    require!(!separator);
    Ok(())
}
fn head(out: &mut Vec<u8>, major: u8, n: u64) {
    if n < 24 {
        out.push(major << 5 | n as u8)
    } else if n <= 255 {
        out.extend([major << 5 | 24, n as u8])
    } else if n <= 65535 {
        out.push(major << 5 | 25);
        out.extend((n as u16).to_be_bytes())
    } else if n <= u32::MAX as u64 {
        out.push(major << 5 | 26);
        out.extend((n as u32).to_be_bytes())
    } else {
        out.push(major << 5 | 27);
        out.extend(n.to_be_bytes())
    }
}
pub fn encode(v: &Value) -> Vec<u8> {
    fn put(v: &Value, o: &mut Vec<u8>) {
        match v {
            Value::Uint(n) => head(o, 0, *n),
            Value::Bytes(b) => {
                head(o, 2, b.len() as u64);
                o.extend(b)
            }
            Value::Text(s) => {
                head(o, 3, s.len() as u64);
                o.extend(s.as_bytes())
            }
            Value::Array(a) => {
                head(o, 4, a.len() as u64);
                for x in a {
                    put(x, o)
                }
            }
            Value::Map(m) => {
                head(o, 5, m.len() as u64);
                for (k, v) in m {
                    head(o, 0, *k);
                    put(v, o)
                }
            }
            Value::Bool(b) => o.push(if *b { 245 } else { 244 }),
            Value::Null => o.push(246),
        }
    }
    let mut out = Vec::new();
    put(v, &mut out);
    out
}
// Same preferred-argument/checked-slice rules as the existing private Core decoder;
// kept test-only so frozen Core parsing and source-authority pins are unchanged.
struct Decoder<'a> {
    wire: &'a [u8],
    at: usize,
}
impl Decoder<'_> {
    fn take(&mut self, n: usize) -> Result<&[u8]> {
        let end = self.at.checked_add(n).ok_or("overflow")?;
        let b = self.wire.get(self.at..end).ok_or("truncated")?;
        self.at = end;
        Ok(b)
    }
    fn node(&mut self, depth: usize) -> Result<Value> {
        require!(depth <= 8);
        let initial = self.take(1)?[0];
        let major = initial >> 5;
        let low = initial & 31;
        if major == 7 {
            return match low {
                20 => Ok(Value::Bool(false)),
                21 => Ok(Value::Bool(true)),
                22 => Ok(Value::Null),
                _ => Err("unsupported simple value"),
            };
        }
        let n = match low {
            0..=23 => low as u64,
            24 => {
                let x = self.take(1)?[0] as u64;
                require!(x >= 24);
                x
            }
            25 => {
                let x = u16::from_be_bytes(self.take(2)?.try_into().unwrap()) as u64;
                require!(x > 255);
                x
            }
            26 => {
                let x = u32::from_be_bytes(self.take(4)?.try_into().unwrap()) as u64;
                require!(x > 65535);
                x
            }
            27 => {
                let x = u64::from_be_bytes(self.take(8)?.try_into().unwrap());
                require!(x > u32::MAX as u64);
                x
            }
            _ => return Err("indefinite or reserved"),
        };
        match major {
            0 => Ok(Value::Uint(n)),
            2 => {
                require!(n <= 16384);
                Ok(Value::Bytes(self.take(n as usize)?.to_vec()))
            }
            3 => {
                require!(n <= 128);
                Ok(Value::Text(
                    std::str::from_utf8(self.take(n as usize)?)
                        .map_err(|_| "utf8")?
                        .into(),
                ))
            }
            4 => {
                require!(n <= 64);
                let mut a = Vec::new();
                for _ in 0..n {
                    a.push(self.node(depth + 1)?)
                }
                Ok(Value::Array(a))
            }
            5 => {
                require!(n <= 64);
                let mut m = BTreeMap::new();
                let mut last = None;
                for _ in 0..n {
                    let k = uint(&self.node(depth + 1)?)?;
                    require!(last.is_none_or(|v| k > v));
                    last = Some(k);
                    m.insert(k, self.node(depth + 1)?);
                }
                Ok(Value::Map(m))
            }
            _ => Err("unsupported major type"),
        }
    }
}
pub fn validate_body(kind: u64, v: &Value) -> Result<()> {
    let m = map(v)?;
    let n = match kind {
        24576 => 16,
        24577 | 24578 => 4,
        24579 => 10,
        24580 => 3,
        24581 => 5,
        _ => return Err("unknown message"),
    };
    exact(m, n)?;
    bounded(get(m, 0)?, 1, 1)?;
    let tm = 253402300799;
    match kind {
        24576 => {
            let op = get(m, 1)?;
            require!(op == &Value::Text("register".into()) || op == &Value::Text("renew".into()));
            text_id(get(m, 2)?)?;
            text_id(get(m, 6)?)?;
            for k in [3, 4, 5, 8, 9, 11, 12] {
                bytes(get(m, k)?, 32, false)?;
            }
            let Value::Bytes(key) = get(m, 7)? else {
                return Err("key");
            };
            require!(!key.is_empty() && key.len() <= 64);
            bounded(get(m, 13)?, 1, 60)?;
            bounded(get(m, 14)?, 0, tm)?;
            if op == &Value::Text("register".into()) {
                require!(get(m, 15)? == &Value::Null)
            } else {
                bytes(get(m, 15)?, 32, false)?;
            }
            let refs = get(m, 10)?;
            let Value::Array(a) = refs else {
                return Err("refs");
            };
            require!(!a.is_empty() && a.len() <= 64);
            let mut previous = None;
            for r in a {
                let Value::Array(pair) = r else {
                    return Err("ref pair");
                };
                require!(pair.len() == 2);
                bounded(&pair[0], 1, 18)?;
                bytes(&pair[1], 32, false)?;
                let encoded = encode(r);
                require!(previous.as_ref().is_none_or(|p: &Vec<u8>| p < &encoded));
                previous = Some(encoded);
            }
            let digest = Sha256::digest(encode(refs));
            require!(&digest[..] == bytes(get(m, 11)?, 32, false)?);
            require!(encode(v).len() <= 16384);
        }
        24577 => {
            bytes(get(m, 1)?, 32, false)?;
            bytes(get(m, 2)?, 32, true)?;
            bounded(get(m, 3)?, 0, tm)?;
        }
        24578 => {
            bytes(get(m, 1)?, 32, false)?;
            bytes(get(m, 2)?, 32, true)?;
            bytes(get(m, 3)?, 32, false)?;
        }
        24579 => {
            for k in [1, 8, 9] {
                bytes(get(m, k)?, 32, false)?;
            }
            for k in [2, 3] {
                bytes(get(m, k)?, 16, true)?;
            }
            bounded(get(m, 4)?, 1, u64::MAX)?;
            let a = bounded(get(m, 5)?, 0, tm)?;
            let z = bounded(get(m, 6)?, 0, tm)?;
            let due = bounded(get(m, 7)?, 0, tm)?;
            require!(z > a && z - a <= 60 && due == a + (z - a) / 2);
        }
        24581 => {
            bytes(get(m, 1)?, 16, true)?;
            bytes(get(m, 2)?, 16, true)?;
            bounded(get(m, 3)?, 1, u64::MAX)?;
            bytes(get(m, 4)?, 32, false)?;
        }
        24580 => {
            bytes(get(m, 1)?, 32, false)?;
            let e = map(get(m, 2)?)?;
            require!(e.len() == 4 || e.len() == 5);
            exact(e, e.len())?;
            bounded(get(e, 0)?, 1, 1)?;
            bounded(get(e, 1)?, 1, 19)?;
            bytes(get(e, 2)?, 16, true)?;
            require!(matches!(get(e, 3)?, Value::Bool(_)));
            if let Some(v) = e.get(&4) {
                bounded(v, 1, 3600)?;
                require!(get(e, 3)? == &Value::Bool(true));
            }
        }
        _ => return Err("message"),
    }
    Ok(())
}
pub fn decode(alpn: &str, wire: &[u8]) -> Result<Value> {
    require!(alpn == ALPN && !wire.is_empty() && wire.len() <= 65536);
    let mut d = Decoder { wire, at: 0 };
    let v = d.node(0)?;
    require!(d.at == wire.len());
    let m = map(&v)?;
    exact(m, 6)?;
    bounded(get(m, 0)?, 1, 1)?;
    let kind = bounded(get(m, 1)?, REQUEST, WITHDRAW)?;
    let rid = bytes(get(m, 2)?, 16, true)?;
    let sid = bytes(get(m, 3)?, 16, true)?;
    require!(rid[..8] == sid[..8] && u64::from_be_bytes(rid[8..].try_into().unwrap()) != 0);
    bounded(get(m, 4)?, 1, u64::MAX)?;
    validate_body(kind, get(m, 5)?)?;
    if kind == 24580 {
        require!(bytes(get(map(get(map(get(m, 5)?)?, 2)?)?, 2)?, 16, true)? == rid);
    }
    require!(encode(&v) == wire);
    Ok(v)
}
