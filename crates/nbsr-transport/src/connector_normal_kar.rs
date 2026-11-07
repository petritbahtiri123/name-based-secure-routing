//! Explicitly pinned local test context. No bootstrap or organization provenance.
use super::*;

pub(super) struct Eligibility {
    receipts: Vec<kar::VerifiedFixtureKar>,
    child_start: u64,
    child_expiry: u64,
}
impl Eligibility {
    pub(super) fn valid_window(&self, t: TimeWindow) -> Result<u64> {
        check(
            self.receipts.len() == 5
                && self.child_start <= t.earliest
                && t.earliest <= t.latest
                && t.latest <= self.child_expiry,
        )?;
        let mut expires = self.child_expiry;
        for receipt in &self.receipts {
            expires = expires.min(receipt.valid_window(t.earliest, t.latest)?);
        }
        Ok(expires)
    }
}
fn fields(j: &J, names: &[&str]) -> Result<()> {
    let m = j.as_object().ok_or("test mapping object")?;
    check(m.len() == names.len() && names.iter().all(|name| m.contains_key(*name)))
}
pub(super) fn verify(trust: &J, bundle: &V, t: TimeWindow) -> Result<Eligibility> {
    check(trust["context_version"] == "normal-roster-kar-v2")?;
    let rows = trust["normal_kar"].as_array().ok_or("normal KAR mapping")?;
    let signers = trust["signers"].as_array().ok_or("normal roster")?;
    check(rows.len() == 5 && signers.len() == 5)?;
    let mut roots = Vec::new();
    let mut operators = BTreeSet::new();
    let mut root_keys = BTreeSet::new();
    let mut child_kids = BTreeSet::new();
    let mut result = Eligibility {
        receipts: Vec::new(),
        child_start: 0,
        child_expiry: u64::MAX,
    };
    for (row, child) in rows.iter().zip(signers) {
        fields(
            row,
            &[
                "authority",
                "operator",
                "kid",
                "key",
                "organization",
                "control",
                "root",
                "payload",
                "wire",
            ],
        )?;
        check(
            row["authority"] == child["id"]
                && row["kid"] == child["kid"]
                && row["key"] == child["key"]
                && row["organization"] == child["organization"]
                && row["control"] == child["control"],
        )?;
        active(child, t, 12)?;
        let root = &row["root"];
        fields(
            root,
            &[
                "operator",
                "kid",
                "key",
                "purpose",
                "active",
                "revoked",
                "generation",
                "sequence",
                "not_before",
                "expires",
            ],
        )?;
        active(root, t, 1)?;
        check(ju(root, "generation")? == 1 && ju(root, "sequence")? == 1)?;
        let key: [u8; 32] = jb(root, "key")?.try_into().map_err(|_| "root key size")?;
        let mut derivation = b"NBSR-FEDERATION-OPERATOR-ID-v1\0".to_vec();
        derivation.push(1);
        derivation.extend(key);
        let operator: [u8; 32] = hash(&derivation).try_into().map_err(|_| "operator size")?;
        check(
            jb(row, "operator")? == operator
                && jb(root, "operator")? == operator
                && operators.insert(operator)
                && root_keys.insert(key)
                && child_kids.insert(jb(child, "kid")?),
        )?;
        // No root may alias another role's operational key.
        for operational in signers.iter().chain(std::iter::once(&trust["log"])).chain(
            trust["witnesses"]
                .as_array()
                .ok_or("witness inventory")?
                .iter(),
        ) {
            check(jb(operational, "key")? != key)?;
        }
        let supplied = kar::SuppliedTestRoot {
            operator,
            kid: jb(root, "kid")?,
            key,
            purpose: 1,
            lifecycle: 2,
            generation: 1,
            sequence: 1,
            not_before: ju(root, "not_before")?,
            expires: ju(root, "expires")?,
            revoked: false,
        };
        let expected = kar::ExpectedKey {
            operator,
            kid: jb(child, "kid")?,
            key: jb(child, "key")?.try_into().map_err(|_| "child key size")?,
            purpose: 12,
            terminal_ids: Vec::new(),
        };
        let receipt = kar::verify_genesis(
            &jb(row, "wire")?,
            &jb(row, "payload")?,
            &supplied,
            &expected,
            t.earliest,
        )?;
        receipt.valid_window(t.earliest, t.latest)?;
        result.receipts.push(receipt);
        result.child_start = result.child_start.max(ju(child, "not_before")?);
        result.child_expiry = result.child_expiry.min(ju(child, "expires")?);
        roots.push(obj(vec![
            (1, V::Uint(1)),
            (2, V::Bytes(operator.to_vec())),
            (3, V::Bytes(supplied.kid)),
            (4, V::Bytes(operator.to_vec())),
        ]));
    }
    roots.sort_by_key(codec::encode);
    check(f(bundle, 33)? == &V::Array(roots))?;
    result.valid_window(t)?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> J {
        serde_json::from_str(include_str!(
            "../tests/fixtures/connector-normal-kar-v2.json"
        ))
        .unwrap()
    }
    #[test]
    fn purpose12_composed_receipts_enforce_both_inclusive_kar_boundaries() {
        let mut trust = fixture();
        // Widen supplied root/child validity so the signed KAR is the limiting evidence.
        for i in 0..5 {
            trust["normal_kar"][i]["root"]["not_before"] = 1699999999u64.into();
            trust["normal_kar"][i]["root"]["expires"] = 1900000001u64.into();
            trust["signers"][i]["not_before"] = 1699999999u64.into();
            trust["signers"][i]["expires"] = 1900000001u64.into();
        }
        let bundle = jv(&trust, "bundle").unwrap();
        for now in [1700000000, 1900000000] {
            let t = TimeWindow {
                earliest: now,
                latest: now,
            };
            let checked = verify(&trust, &bundle, t).unwrap();
            assert_eq!(checked.valid_window(t).unwrap(), 1900000000);
            assert!(
                checked
                    .valid_window(TimeWindow {
                        earliest: 1699999999,
                        latest: 1700000000
                    })
                    .is_err()
            );
            assert!(
                checked
                    .valid_window(TimeWindow {
                        earliest: 1900000000,
                        latest: 1900000001
                    })
                    .is_err()
            );
        }
        for now in [1699999999, 1900000001] {
            assert!(
                verify(
                    &trust,
                    &bundle,
                    TimeWindow {
                        earliest: now,
                        latest: now
                    }
                )
                .is_err()
            );
        }
    }
}
