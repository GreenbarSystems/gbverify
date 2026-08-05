# Changelog

All notable changes to gbverify are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-08-05

### Fixed

- **Cross-language canonicalization divergence on `-0.0`.** Prior to this
  release the Node CLI serialized negative zero as `-0` while the Python
  CLI serialized it as `-0.0`, producing different SHA-256 hashes for
  otherwise-identical manifests. Both CLIs and the source-of-truth
  Greenbar-Pay assembler now normalize `-0` to `0` before serialization.
  This is the only known input class where JS `JSON.stringify` and
  Python `json.dumps` disagree on data that the assembler could plausibly
  emit (via e.g. `-round2(x)` where `x` rounds to zero).

  Detection: the paired `-0.0` fixture in `test.sh` (Test 7) would go red
  if either implementation regresses.

  No `schemaVersion` bump is required — `-0` and `0` are equal-valued
  under JSON's data model, and no previously-sealed packet's recorded
  `manifestHash` changes as a result of this fix except in the specific
  case where `-0` was ever emitted, which we have no evidence of in the
  wild (see PR description for the audit trail).

### Notes

- Version bumped in `cli-node/package.json`, `cli-python/pyproject.toml`,
  `cli-node/bin/gbverify.js`, and `cli-python/gbverify.py`.
- CI (cross-language-hash-agreement) is unchanged; the new fixture ships
  inside `test.sh` and runs on every push and PR.

## [0.2.1] — 2026-08-05

- Publish config + PyPI packaging + automated release workflow. Never
  successfully published to npm/PyPI due to missing trusted-publisher
  rules on both registries; see 0.3.0 release for the first successful
  publish.

## [0.2.0] — 2026-08-05

- Product rename: Greenbar Pay → Greenbar AP Assurance. Sample packetId
  pinned for deterministic fixture hashes across runs.

## [0.1.0] — 2026-08-05

- Initial MIT-licensed release of the cross-language verifier for
  Greenbar AP Assurance evidence packets. Node and Python CLIs; sample
  packet; six-scenario cross-language test suite.
