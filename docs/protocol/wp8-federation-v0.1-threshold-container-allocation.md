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
| `valid-registrar-1-of-1` | `15d8ba07e83668fb1b7848194e20398feaf45bcaba00888bdb379c8797ec75c2` | ACCEPT | `NONE` | false |
| `valid-witness-2-of-3` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | ACCEPT | `NONE` | false |
| `valid-global-trust-3-of-5` | `c30d36a4b97d88f937032b8a3336c97d4a160720cff37ab8023e4243cabcc5a6` | ACCEPT | `NONE` | false |
| `valid-high-risk-trust-4-of-5` | `097f6412b78cb54ffd160a362843518365a8fea3b5ce72b697f2d61e45d72638` | ACCEPT | `NONE` | false |
| `valid-recovery-plus-registry-plus-witness` | `e89b7bff25f5578b73682b526849d379b7f88dc5e387d639fe11f265f5a251fd` | ACCEPT | `NONE` | false |
| `valid-over-threshold` | `681539b19766d21c831629e8472cfef731a667474af297d565695da0d40f5894` | ACCEPT | `NONE` | false |
| `valid-high-risk-witness-3-of-5` | `3d196f0b44ad821dc6b05d6b139fa58f941ef3a7850744e584abb0e44524206a` | ACCEPT | `NONE` | false |
| `valid-deny-only-emergency-2-of-5` | `e1f7d8cedf5de904c6dd025b822eb1cf89ae7194c2d16bcae38ecc56a034282c` | ACCEPT | `NONE` | false |
| `valid-conflict-plus-witness` | `a8cbabd3914944e894341d5d497855adab46c7af2b7143f9b5b94332285ed3e3` | ACCEPT | `NONE` | false |
| `valid-appeal-plus-witness` | `082d1477aa048a781a144a8dced3eb19c6edd7700eb49d67ae032b5c5ca5b61d` | ACCEPT | `NONE` | false |
| `valid-input-order-normalizes` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | ACCEPT | `NONE` | false |
| `pending-zero-signatures` | `44e8b0faf553a2a374abfa4f10a34639fa83edbd88d37588a1584125a59c0385` | PENDING | `ERR_EVIDENCE_MISSING` | false |
| `invalid-insufficient-threshold` | `850d367f135a579ec81b237b057ce4b458c94cb2d8787d99a7f426e599f7d704` | PENDING | `ERR_WITNESS_THRESHOLD` | false |
| `invalid-duplicate-signer` | `39555b3107b286e1485e4f3180416bbd41fd8c9e7212986bfce9ee55269bef7a` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-same-organization-twice` | `f24993ce1d8355df7136eca4e336a31b1f51345ebd9b8dcc0a08c660eb7b9558` | REJECT | `ERR_WITNESS_THRESHOLD` | false |
| `invalid-wrong-authority-class` | `767472ffe51855d534f16199d1661b2880011d2b587ad364bb448033811ab0a3` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-wrong-purpose` | `95efe2bc29bf99b0107ee77e0d9b300b881713172e74e5e5c23b7bb2ebafbc54` | REJECT | `ERR_KEY_PURPOSE` | false |
| `invalid-bad-kid` | `062b3dd82cb76af6a8090906a8c05643a19fa90266c84021b05b952e44a7fff8` | REJECT | `ERR_IDENTITY` | false |
| `invalid-revoked-signer` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | REJECT | `ERR_REVOKED` | false |
| `invalid-expired-signer` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | REJECT | `ERR_FRESHNESS` | false |
| `invalid-wrong-payload-digest` | `6376ab52e0c16f1c588449a6cc54a0ea71352f9049d06c90d0cd8f6f01f09c21` | REJECT | `ERR_SIGNATURE_INVALID` | false |
| `invalid-mixed-payload-digests` | `8c3da0634fe3538eb5fb20f4a6a85cad8bdffface1623b76f5ece624fccb2ec7` | REJECT | `ERR_SIGNATURE_INVALID` | false |
| `invalid-wrong-generation` | `8d5a6c4bc7554c4d3cb300158d4106c0419a51609c51033d69d84a91dcdbb602` | REJECT | `ERR_REPLAY` | false |
| `invalid-wrong-scope` | `08b4edcebd8c1c18073139ecfb77e1a61d9a6f1943fe8022f8c93c507fc1e598` | REJECT | `ERR_SCOPE` | false |
| `invalid-wrong-action` | `d2c8ab539186798c4e81c740322c4dbafc009b0c6c087da23114019169b5d783` | REJECT | `ERR_REPLAY` | false |
| `invalid-signature` | `f78b0567331c1f24212121b2840bf33fb11a09b0cb44bbd0b95ab2921d6c0313` | REJECT | `ERR_SIGNATURE_INVALID` | false |
| `invalid-unsupported-critical-extension` | `0a0993da5ee626bd795c791401f273ce9575c7fc3de817f7f71e6411bfc8e555` | REJECT | `ERR_UNSUPPORTED_CRITICAL` | false |
| `invalid-excessive-signer-count` | `7b989225a09a63e00772656dacfc036ef51635bee5fa3ac49b7ecb4b28cb20d8` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-malformed-signer-entry` | `da4558948020dacb6e565cb242fdea78d56a232d02fd693949c6f93393ea6ab7` | REJECT | `ERR_SCHEMA` | false |
| `invalid-replay-authorization-context` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | REJECT | `ERR_REPLAY` | false |
| `invalid-unsupported-container-version` | `5fe056b9054bde7e9deca87893370377d246d22f5fd43291f173232ce4130bd9` | REJECT | `ERR_VERSION` | false |
| `invalid-wrong-group-order` | `076e52312e1f54968e478242a509c65bd241bf4a946f0eda3ea020016c85230c` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-cross-group-signer-reuse` | `7d998383799cf387e075dbf7ef204c31c86b0052bc06dd224c437d36352e1332` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-ineligible-authority-id` | `b761944573ddfd969beff61a74f61e8db38489b80b8484d3f84ed6dbd9ea3405` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-required-class-count` | `be0e1dfd3731f8fc1f0a906ab57bdfc084f3ebeb78d20064bf31807523249592` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-group-scope-digest` | `eb75f38f9d8695349a90eea14037b083ba23ed9560caaef8e8c5b91964739d01` | REJECT | `ERR_SCOPE` | false |
| `invalid-authorization-window` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | REJECT | `ERR_FRESHNESS` | false |
| `invalid-deny-only-add-action` | `ff3fedf687155b3270d83effd7491145de82733047b439f49b44bcc6a7077a82` | REJECT | `ERR_POLICY_EXPANSION` | false |
| `invalid-excessive-group-count` | `9746644b8322017cb584731baac65bdee721bcc2781bd472ef9ec5a8f0522af1` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-excessive-total-signers` | `b469ee80fc1431e9605021bc6178b1275e3fcbd8b52549ed1be6dd27d5350eb5` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-excessive-nested-depth` | `150d657756206f4d4cec1760aa839fdc1fc0fa44236271f534be98efeb2da10c` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-policy-object-substitution` | `3a7611535fe7a851f0fc1878c0bffe7331bee979cc25bfdbec5ca2212b7b6855` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-policy-message-substitution` | `f0811b6efc71ab261f31b0ca15be72559eb3bc46cc425667a5225d56ceb14a3a` | REJECT | `ERR_REPLAY` | false |
| `invalid-missing-required-capability` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | REJECT | `ERR_UNSUPPORTED_CRITICAL` | false |
| `invalid-eligible-count-exceeded` | `d92b711e1b23172bc2c810685c1da067e3a85cc1873bf3e1d219ab2c7d25f4ab` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-malformed-extension` | `5ff18c56b3a4561a725c24c0b5041c0d2c2134ef3dfc9c74a4b5fddc1f121bff` | REJECT | `ERR_SCHEMA` | false |
| `invalid-oversize-authority-id` | `ca3858cda5893f1b1a213fc0d842d610ff036f89c45b64247f83fae66a4db8ba` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-oversize-organization-id` | `8ca2357b6d26e2d131a0930da00b428d513e86ec82a1822b1268f4f8af1e1e2b` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-oversize-kid` | `74accbe80868659d2f911bc370b0a862c5314d984b89c09286177b082003d097` | REJECT | `ERR_RESOURCE_LIMIT` | false |
| `invalid-weakened-class-count` | `919d09b023c7e52179c9b4e65e970e0ceec679ce03e547d677ff9d3d6e533724` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-weakened-organization-diversity` | `806508ba650dfe71c6ea5eeb4a82e9afeb844f4c54e9eda4bc67765f20492755` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-self-selected-eligible-set` | `dae0d6de3c377944e766275c58de9441128c2d490fa4e1b6cfd2b211a3161e95` | REJECT | `ERR_AUTHORITY` | false |
| `invalid-noncanonical-cose-sign1` | `02dd3af6133a5e421743d96ccfbff50b4114f2520ca93fda899943364c6162b8` | REJECT | `ERR_NON_CANONICAL` | false |
| `invalid-unknown-policy-key` | `906dcc0fbc8b595423ecf2338ac1eadd0aa9e8d9f36087e50a809a8544465950` | REJECT | `ERR_SCHEMA` | false |
| `invalid-unknown-group-requirement-key` | `76c3d583f00f3e52ab1ca47bca601ee2d78fd0a964b0db529bdb00c0e3056429` | REJECT | `ERR_SCHEMA` | false |
| `invalid-unknown-lineage-key` | `4db1c2995673c4a44ac6d0b51c9937d8c7a0be10c9f2b8597fba9b481cb7b839` | REJECT | `ERR_SCHEMA` | false |
| `invalid-unknown-authorization-key` | `47bfbac4bf2a6c115a95e57ebb50cd565cb72fb6ebd830aaa121b78202b07d5c` | REJECT | `ERR_SCHEMA` | false |
| `invalid-malformed-policy-extension` | `bc8a1eb64db8aa3162fe38f105d1738f16cdf295ec7b158d814fcdcd049f3df7` | REJECT | `ERR_SCHEMA` | false |
| `invalid-malformed-group-extension` | `196a9853d62159b981e036d350183408cfc44e542f387633995959915940a42c` | REJECT | `ERR_SCHEMA` | false |
| `invalid-malformed-authorization-context` | `ff2196d7489119cbca596b8383684f501f4d926696eba64c06ff2cc60ad55a8e` | REJECT | `ERR_SCHEMA` | false |
| `invalid-lineage-field-types` | `10a904685ba6f099651902f92c3a356f6b4540604dfcc922c12005a0bc7fa337` | REJECT | `ERR_SCHEMA` | false |
| `invalid-short-request-id` | `cfc8341b07300f790a7080e425c2ff9213de06c609dbd30321d3188d463da397` | REJECT | `ERR_SCHEMA` | false |
| `invalid-authorization-time-type` | `d13921bf9f36ad55fd3f85557bc67e9eebf7026c4cb65e27d4ed7035f279e58b` | REJECT | `ERR_SCHEMA` | false |
| `invalid-authorization-window-order` | `e5553c1c41262d90ad7ed4a59148a687388b2b77af0a2f469f95e1b524566d7b` | REJECT | `ERR_SCHEMA` | false |
| `invalid-extension-version` | `86f520ba41a7f110538eb7acf89fd755d810e6c77c41744710142c215080d3ac` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-container-version` | `45803dee9b80df2a0dcad8e8496dd7d79fad1e8216a497a260208d5ab04f80d9` | REJECT | `ERR_VERSION` | false |
| `invalid-boolean-policy-version` | `00923a58a327eb1906742a93fba131012396fd1cd340dfbc63aeef077c570a07` | REJECT | `ERR_SCHEMA` | false |
| `invalid-nondict-signature-context` | `0af62986a108531b5d946a26494e21da799eff71af488257c07016f0b6845de2` | REJECT | `ERR_SCHEMA` | false |
| `valid-multiple-keys-one-authority-identity` | `972c195d28fdf90f35a1ab2a6c04ce913263a9f2a45df111e19c758b9c23d0a8` | ACCEPT | `NONE` | false |
| `invalid-negative-not-before` | `560b1515ba17d15d0564e4c95f6522822b1fe87613985feb630f94ea00d3c02f` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-object-class` | `77cab09c18fa9ae335d65552158fa79c2d8fed55c77919edcea3c99b4eb2e497` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-required-count` | `0f3f2bd11feb90e78805b54185bddee3324ff42c850a0c08043949f7ec17e75f` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-eligible-count` | `e0e92c9832b2d8e622eb2f855ed2fcdc1a3f2d79051f1960f56a2f01a7a6c8cd` | REJECT | `ERR_SCHEMA` | false |
| `invalid-boolean-minimum-organizations` | `24dd0817a2a0a12abf373d1ffa7eba9c1601d9a507d93c3e617c2a1c6f5bf7c1` | REJECT | `ERR_SCHEMA` | false |
| `invalid-mixed-eligible-id-types` | `5e71ec9b7ef0cb299e6e6dc4f572402e1609ec5e3bf2b655afc64bb2c90b0b1d` | REJECT | `ERR_SCHEMA` | false |
| `invalid-empty-authority-id` | `53c05f442e572d2395b86db0387df295331eb7e8dab6a15db53ea554c90d6832` | REJECT | `ERR_SCHEMA` | false |
| `invalid-empty-kid` | `02c2cd32fe1862d5f237ab24a9b4458faa3bd3a27f2b1af0b45f6144e95ea01a` | REJECT | `ERR_SCHEMA` | false |
| `invalid-empty-organization-id` | `689175149344aa10e2265f9d1ae71ccfeab69e5b7b2c48bc95ab8dc3ce333eb4` | REJECT | `ERR_SCHEMA` | false |
