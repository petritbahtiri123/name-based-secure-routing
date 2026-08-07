# Federation v0.1 Threshold Container Allocation

> **PROPOSED — REQUIRES HUMAN APPROVAL**

Generated from `registries/federation-v0.1-threshold-container-proposal.json`.

## Container fields

| Key | Type and rule |
|---:|---|
| 1 | `container_version:uint=1` |
| 2 | `profile_id:tstr=nbsr-federation-dev-v1` |
| 3 | `target_object_class:uint:registered-object-type` |
| 4 | `payload_digest:bstr32:sha-256-canonical-target-payload` |
| 5 | `threshold_policy:ThresholdPolicy` |
| 6 | `authority_scope_digest:bstr32` |
| 7 | `lineage:LineageContext` |
| 8 | `authorization_context:AuthorizationContext` |
| 9 | `threshold_groups:[ThresholdGroup]` |
| 10 | `extensions:[ExtensionEntry]:optional` |

## Literal fixture digests

| Fixture | SHA-256 | Decision | Reason | Mutation |
|---|---|---|---|---|
| `valid-registrar-1-of-1` | `660f1b9ab9ea2698a930739c49c12a794ff549013b6b9e27cbca1524c0849b41` | ACCEPT | `NONE` | false |
| `valid-witness-2-of-3` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | ACCEPT | `NONE` | false |
| `valid-global-trust-3-of-5` | `0df4a6163121f22b07995f7bfb616fd050b602be7e6661ef3bf7e9f33a2a10e2` | ACCEPT | `NONE` | false |
| `valid-high-risk-trust-4-of-5` | `50905fea3d9e80836b4ad25cc36f7ab9b96137a89339137da6ec8be2fe65eb29` | ACCEPT | `NONE` | false |
| `valid-recovery-plus-registry-plus-witness` | `e2d6799e0195da255edb70e7fbf0308c0a4a0e13080a66fbeecbbf54c5a36314` | ACCEPT | `NONE` | false |
| `valid-over-threshold` | `0309e0ce044a94f248d6be99463658f3054206d3c3dcd5d459890d5464ca0361` | ACCEPT | `NONE` | false |
| `valid-high-risk-witness-3-of-5` | `2831d813cf6723083f315f1e65bd18aa897128e849581027445a69785845247a` | ACCEPT | `NONE` | false |
| `valid-deny-only-emergency-2-of-5` | `f574e9136bae770d12ff7ec89f7e8528e23cc4323c7a53a7899f3e7911217972` | ACCEPT | `NONE` | false |
| `valid-conflict-plus-witness` | `b61a1a0fee47db21a2ef2d8eee7c1a0d3c7ef99b65f4fb31254e78109909d55c` | ACCEPT | `NONE` | false |
| `valid-appeal-plus-witness` | `3af28cf9d90caa4f69114f908c94b82f7d7627d9593a17244a1339b261a39469` | ACCEPT | `NONE` | false |
| `valid-input-order-normalizes` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | ACCEPT | `NONE` | false |
| `pending-zero-signatures` | `44e8b0faf553a2a374abfa4f10a34639fa83edbd88d37588a1584125a59c0385` | PENDING | `ERR_EVIDENCE_MISSING` | false |
| `invalid-insufficient-threshold` | `68407796a9c4619709e0fc2596953559b36c6751c07cb94b5540a2bf604fdf50` | PENDING | `ERR_WITNESS_THRESHOLD` | false |
| `invalid-duplicate-signer` | `5aa552127441a0519d478a903c1b680e7668b7604af977aba8dbb8d3da61c576` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-same-organization-twice` | `35ff92ee4c130e444d704b9c483e593f59f75487bc85d1f6acea684787de761d` | REJECT | `ERR_WITNESS_THRESHOLD` | false |
| `invalid-wrong-authority-class` | `a14ab79feacd96e77a04d98034cd1fb624f484a821c602a94f4d99d8b155009f` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-wrong-purpose` | `cf032f3a45700450b23a15d8bd64a291925b22edf271504ac8be832d8fd680a7` | REJECT | `ERR_KEY_PURPOSE` | false |
| `invalid-bad-kid` | `5d935349099c0ffdc8b1ab16b96a3686c4d590e12eceec3a5814285e4126fce4` | REJECT | `ERR_IDENTITY` | false |
| `invalid-revoked-signer` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_REVOKED` | false |
| `invalid-expired-signer` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_FRESHNESS` | false |
| `invalid-wrong-payload-digest` | `79edc2350db625125724a0660f5baec48803af1a96ca43e73efb12af62521f45` | REJECT | `ERR_SIGNATURE_INVALID` | false |
| `invalid-mixed-payload-digests` | `53a4386a2218b02d3f956c80971d851af333f9627292f3e80cf1ed85ba89698d` | REJECT | `ERR_SIGNATURE_INVALID` | false |
| `invalid-wrong-generation` | `b065d9a683a862b6f520be2d608be3a65ae28c03faa367c6cd648ce8c202f3f9` | REJECT | `ERR_REPLAY` | false |
| `invalid-wrong-scope` | `cac55866f88994740c4741c1f8476787974932186af5198f4ad9b0d3071bc895` | REJECT | `ERR_SCOPE` | false |
| `invalid-wrong-action` | `9a671be1059b14bb51191cf48fa9748f2520a8e89a3ea7732143b90bbcb51393` | REJECT | `ERR_REPLAY` | false |
| `invalid-signature` | `6aeaf86577aa6905da3d59f3dc86cc4fb526700e0c76dcaae628cce89abeb144` | REJECT | `ERR_SIGNATURE_INVALID` | false |
| `invalid-unsupported-critical-extension` | `a4835efadc77084a4efe1695ff7dff40c2126960f7c9cbab4196959da616038d` | REJECT | `ERR_UNSUPPORTED_CRITICAL` | false |
| `invalid-excessive-signer-count` | `793431f959c1216cde791428ae9f67658eb59dcbd5ad6f656a3d5361ccb2703e` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-malformed-signer-entry` | `b0d7198467a5b4ba918aa126006e5e2b497b1aab6b4b7577efb4350373805691` | REJECT | `ERR_SCHEMA` | false |
| `invalid-replay-authorization-context` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_REPLAY` | false |
| `invalid-unsupported-container-version` | `3d1d02b980a86937b4a9ce283fe52e097facac9750e7e17e8d6ef1367de35729` | REJECT | `ERR_VERSION` | false |
| `invalid-wrong-group-order` | `ac3db850df5dc4687ff163072e7df06aa4cd3a7834116a7dbfa4c36deba9ec82` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-cross-group-signer-reuse` | `eaa6c8a4fcecd1a35f68e08c75dfcf2cd9d8c88109261ed0ec6c7907f796233a` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-ineligible-authority-id` | `025318f3d23358370f7c48bc49e660504f446eea0b196f1d18de736523567b8b` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-required-class-count` | `3588d1a7943ae5927718e11933b2fdbede9e259d54ee772795b936fa349910f0` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-group-scope-digest` | `ad1e328a3ea3235c22a0666f4404ccb00702f542f6f4caf51d9627ab5709ef09` | REJECT | `ERR_SCOPE` | false |
| `invalid-authorization-window` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_FRESHNESS` | false |
| `invalid-deny-only-add-action` | `475cb0b149e9befeb68a7f3d0f48d8ba13cee1c2be4cdb5e95707ab36c0638ef` | REJECT | `ERR_POLICY_EXPANSION` | false |
| `invalid-excessive-group-count` | `6af7b1f6d01978ab29ec893090551d87ef0783db707e2273a6269b4b6cebe6a4` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-excessive-total-signers` | `e73e50327fe7bff8a5e3badeea11cf039f5149cd58ff513f25d10cc9ac2910d4` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-excessive-nested-depth` | `eb4f4081cac9a667f89a97c63c16c35e3588817f5c72d40076767359ce144beb` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-policy-object-substitution` | `bd8e5b7d9c5a54ac10a11fe44d835050798811d288b05f8adc2f17b3b5bc39f8` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-policy-message-substitution` | `26c52ba6017c9ddf2c2f985061f5d37255b7b6e13e52cabbb804bd033580d41b` | REJECT | `ERR_REPLAY` | false |
| `invalid-missing-required-capability` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_UNSUPPORTED_CRITICAL` | false |
| `invalid-federation-objects-only` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_UNSUPPORTED_CRITICAL` | false |
| `invalid-pre-capability-agreement` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_DOWNGRADE` | false |
| `invalid-wrong-agreed-profile` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_VERSION` | false |
| `invalid-wrong-agreed-federation-version` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_VERSION` | false |
| `invalid-wrong-selected-core-version` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_VERSION` | false |
| `invalid-capability-stripping` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_DOWNGRADE` | false |
| `invalid-cross-session-replay` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_REPLAY` | false |
| `invalid-malformed-capability-collection` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_SCHEMA` | false |
| `invalid-single-sign1-downgrade` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_DOWNGRADE` | false |
| `invalid-replay-without-threshold-capability` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | REJECT | `ERR_UNSUPPORTED_CRITICAL` | false |
| `invalid-signature-context-capability` | `9cfe26ab4c6215457ec060fc7e912600e7546355affe0b866b8f11e0a4c2a964` | REJECT | `ERR_DOWNGRADE` | false |
| `invalid-eligible-count-exceeded` | `484f27e767cd84afccf29aeaf8a502bd8d40803c834faf650e2f970ce4191fd9` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-malformed-extension` | `a74178b1a7179a82c8f1ffba9037130b43c3d68b4322946664cd32dd28c68009` | REJECT | `ERR_SCHEMA` | false |
| `invalid-oversize-authority-id` | `fb47a69eed1629a4c5ce12511dbf0405763291df1cdef2500a02fa5796a79cfe` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-oversize-organization-id` | `2df77366092aa77e679ce5981727969860de2195ea37a0c0a5d5fcedb65c4841` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-oversize-kid` | `4e739dde486caec52eb8b544fca66350f40df667f094ead53619ff1942595b71` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-weakened-class-count` | `1852de92c63a8a387e2032cd4c8d28e81038d14f3faba755df115278b29d8af0` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-weakened-organization-diversity` | `0364e589e4a2f7c33824dedd1e3042bb97c4806f7671afad743a2fc999bf2ab5` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-self-selected-eligible-set` | `aae811b0b7fab822bdefcef5a88386565162055d95eba7f8c1024dfc4cf1df75` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-noncanonical-cose-sign1` | `1ad25feaf10762bf2fc7978c433744f20fd4d3b92ba62aa28dd48090a8c2b4dc` | REJECT | `ERR_NON_CANONICAL` | false |
| `invalid-unknown-policy-key` | `78687cc09ff222cbb9ab515ca5dbeceafd329bf79a2640b43107fee3fd7b33a8` | REJECT | `ERR_SCHEMA` | false |
| `invalid-unknown-group-requirement-key` | `c4b09af3a93c38cafbc8d6d85cbb24d1d355131fe98d1096f85ce1b840116f99` | REJECT | `ERR_SCHEMA` | false |
| `invalid-unknown-lineage-key` | `88bba42391c1c29b9e6c54500fe7e7f6574472c01aa36c81b98eb416bbb8fafb` | REJECT | `ERR_SCHEMA` | false |
| `invalid-unknown-authorization-key` | `3f4e34b17e328cf85778d12353c2e143e1d82f946fe2b9550c3b374b755658cd` | REJECT | `ERR_SCHEMA` | false |
| `invalid-malformed-policy-extension` | `68fb6bbd887fb716355b0ec190acb4dd93ff25f2c38a3def708aece5030b36b9` | REJECT | `ERR_SCHEMA` | false |
| `invalid-malformed-group-extension` | `8a751ab905e9d9e1cc5e1caf38294ede8027ce3febcfefd200ab587a42374098` | REJECT | `ERR_SCHEMA` | false |
| `invalid-malformed-authorization-context` | `55da771c051454432d71e416ca3f72fccbf7b685d3a59448ccb323500830aeac` | REJECT | `ERR_SCHEMA` | false |
| `invalid-lineage-field-types` | `c92bb8769364c6561cc88c8cdb89c5bd3631dd1fd8983a570fd1ed56efb3581c` | REJECT | `ERR_SCHEMA` | false |
| `invalid-short-request-id` | `d8d015da468127e8a9dfcf292b0230f2d599043ca1698c2e064ae16b6ea92e53` | REJECT | `ERR_SCHEMA` | false |
| `invalid-authorization-time-type` | `38a582a45d43817ac98555b0925e0894880bc82916072a8c8c2c1d6665448ab7` | REJECT | `ERR_SCHEMA` | false |
| `invalid-authorization-window-order` | `11549daa5b50482fe9264a19684230b8c1df219e59cd1c40ef2775d92420e467` | REJECT | `ERR_SCHEMA` | false |
| `invalid-extension-version` | `ebb63028c599511dcb9decc3bf998ef63a2a8e3a4d4dc74c075205ff8dee7222` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-container-version` | `5d02ae884a18c2b4d9b593d845ea74fea5c6502daccf1991f3898bc78f49bb41` | REJECT | `ERR_VERSION` | false |
| `invalid-boolean-policy-version` | `667edf3f3cab408a3d0feeba949f625bb7d05f7d6636fb6432c22bcf57e7f8f3` | REJECT | `ERR_SCHEMA` | false |
| `invalid-nondict-signature-context` | `76a51a7ead8663b3bab8bf800e4a9f0eb7668e5f1f8b0dfcb4b7250551473eda` | REJECT | `ERR_SCHEMA` | false |
| `valid-multiple-keys-one-authority-identity` | `0b2eaa31e49b029f211c125b7047979bda7aaa8f3c68b6c96a4610eb78363782` | ACCEPT | `NONE` | false |
| `invalid-negative-not-before` | `e605b045a8a3117d9e04b10005167d84e9b4a834faf83bab60c2bacd127fac74` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-object-class` | `90deb0727ed60a56fb90ff6143c54d7db79f400d19d5106ce9335c0aaa157e8f` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-required-count` | `6245532ab228bf2a51735559f9ca880383fb041e9a44c1093d9b07f29a8eab49` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-eligible-count` | `84bf5b61dba0ba8ff11c0bd2aa0887fa091cbd2bb9d8bd59bbef320904b5ccaa` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-minimum-organizations` | `60ca021f80dc2476a2d81ae103842f0bde250773c9937c1569cca9ff46f8d531` | REJECT | `ERR_SCHEMA` | false |
| `invalid-mixed-eligible-id-types` | `9e68d7c75a750da44ed18b56c4a979044cb53d715785942cb764ffd8fa684d8e` | REJECT | `ERR_SCHEMA` | false |
| `invalid-empty-authority-id` | `694b85b3b214d33b0bb60c100ad582022bd3968819ed9a75ff561f841e70186a` | REJECT | `ERR_SCHEMA` | false |
| `invalid-empty-kid` | `85559db5f74cb1b142dff6d688a2983178bbe552d2f486e536d26b2f6f44c8e3` | REJECT | `ERR_SCHEMA` | false |
| `invalid-empty-organization-id` | `9942334e347ec756ff4b83c96e408b46e6d6acf0b17ae4bd1132ae328dc74178` | REJECT | `ERR_SCHEMA` | false |
