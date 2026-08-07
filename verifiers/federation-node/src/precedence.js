export const FROZEN_PRECEDENCE=[
  ["resource-parsing","ERR_RESOURCE_LIMIT"],["canonical-encoding","ERR_NON_CANONICAL"],["crypto-signature","ERR_SIGNATURE_INVALID"],["identity-key-lifecycle","ERR_IDENTITY"],["schema-version","ERR_SCHEMA"],["authority-scope","ERR_AUTHORITY"],["generation-sequence-continuity","ERR_ROLLBACK"],["revocation-terminal","ERR_REVOKED"],["transparency-witness","ERR_TRANSPARENCY"],["freshness-outage","ERR_FRESHNESS"],["local-authorization","ERR_LOCAL_POLICY"]
].map(([className,reason],index)=>({class:className,reason,rank:index+1}));
export function verifyPrecedenceFixture(fixture) {
  if (fixture.format_version !== 1 || fixture.precedence.length !== 11 || fixture.vectors.length !== 11) throw new Error("precedence fixture structure/count mismatch");
  for(let i=0;i<FROZEN_PRECEDENCE.length;i++){const actual=fixture.precedence[i],expected=FROZEN_PRECEDENCE[i];if(!actual||actual.class!==expected.class||actual.reason!==expected.reason||actual.rank!==expected.rank)throw new Error("frozen precedence mismatch");}
  const ranks = new Map(FROZEN_PRECEDENCE.map((item) => [item.reason, item]));
  for (const vector of fixture.vectors) {
    const candidates = vector.defects.map((reason) => ranks.get(reason));
    if (candidates.some((item) => !item)) throw new Error(`${vector.id}: unknown precedence defect`);
    const selected = candidates.reduce((left, right) => left.rank < right.rank ? left : right);
    if (selected.reason !== vector.expected_reason) throw new Error(`${vector.id}: precedence mismatch`);
  }
  return fixture.vectors.length;
}
