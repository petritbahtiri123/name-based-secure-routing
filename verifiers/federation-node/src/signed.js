import { decodeCanonical } from "./cbor.js";
import { publicKeyFromRaw, verifySign1 } from "./cose.js";
const PUBLIC_KEY=publicKeyFromRaw(Buffer.from("43046bfe4092b3e94994eada15dcc20d8aaa07b658fd3954eb8e0efb8bdca5de","hex"));
const VALID_KID=Buffer.from("a1b2c3d4e5f60708","hex");

export function verifySignedFixture(fixture) {
  if(fixture.format_version!==1||fixture.vectors.length!==12||fixture.object_coverage.length!==18)throw new Error("signed fixture structure/count mismatch");
  const key=PUBLIC_KEY;
  for(const vector of fixture.vectors){let outcome="ACCEPT",reason="NONE";try{const result=verifySign1(Buffer.from(vector.cose_sign1_hex,"hex"),key);decodeCanonical(result.payload);if(result.payloadDigest!==vector.payload_sha256)throw new Error("payload digest mismatch");if(!result.kid.equals(VALID_KID)){outcome="REJECT";reason="ERR_IDENTITY";}else if(vector.purpose===0){outcome="REJECT";reason="ERR_KEY_PURPOSE";}}catch(error){outcome="REJECT";reason=/signature invalid|payload digest/.test(error.message)?"ERR_SIGNATURE_INVALID":"ERR_PARSE";}
    if(outcome!==vector.expected||reason!==vector.expected_reason)throw new Error(`${vector.id}: signed result mismatch: ${outcome}/${reason}`);
  }return fixture.vectors.length;
}
