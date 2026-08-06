# Changelog

All notable changes to gbverify are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [0.3.3] — 2026-08-06

Documentation and CLI banner text only. No change to canonicalization,
hashing, or verification behaviour — byte-identical output to 0.3.2 for
every packet.

### Changed

- **Dropped "Greenbar AP Assurance" from the README, the Node CLI's
  `--help` banner, and the Python CLI's module docstring (also its
  `--help` output).** gbverify's actual check is
  `schemaVersion === "evidence.v2"` — it was never coupled to one
  product in code, only in its own wording. The banner text claimed a
  dependency the tool doesn't have: any Greenbar product that seals an
  `evidence.v2` packet is verifiable, not only the one the docs
  happened to name.
- README also now says plainly that `test.sh`'s cross-language check
  (Node vs Python agreeing with each other) is not the same claim as
  agreeing with a live copy of `assemble.ts` in Greenbar-Pay — the two
  repos stay in sync by convention today, not by an automated
  cross-repo test.

### Notes

- Version bumped in `cli-node/package.json`, `cli-python/pyproject.toml`,
  `cli-node/bin/gbverify.js`, and `cli-python/gbverify.py` because
  `--help`/`--version` output text changed, even though verification
  logic did not.

## [0.3.2] — 2026-08-06

Completes the release started by 0.3.1. No functional or canonicalization
changes — byte-identical verification behaviour to 0.3.0.

### Fixed

- **npm Trusted Publishing failed in `release.yml`.** Two causes, both in
  the `publish-npm` job:
  - `actions/setup-node` was given `registry-url`, which writes an
    `.npmrc` containing `_authToken=${NODE_AUTH_TOKEN}`. With no token
    supplied, npm authenticated using setup-node's literal placeholder
    and the registry rejected the write. npm reports unauthorized writes
    as `E404`, so the failure presented as a missing package.
  - OIDC Trusted Publishing requires npm >= 11.5.1; Node 22 bundles
    npm 10.x, which has no OIDC support. The job now upgrades npm before
    publishing.

  Note for future debugging: provenance signing succeeded during the
  failed run. Provenance works on npm 9.5+ and is independent of the
  Trusted Publishing auth path, so a signed provenance statement is not
  evidence that publishing is correctly configured.

### Notes

- 0.3.1 published to PyPI but not to npm. The two registries are aligned
  again from 0.3.2 onward. `v0.3.1` was left in place rather than
  force-moved; the tag reflects what was actually released.
- Action pins moved to current majors in both workflows: `checkout@v7`,
  `setup-node@v7`, `setup-python@v7`, `action-gh-release@v3`. Clears the
  Node 20 runtime deprecation warnings. `pypa/gh-action-pypi-publish`
  stays on `release/v1`, which is that project's supported moving ref.

## [0.3.1] — 2026-08-05

Release-pipeline verification. No functional or canonicalization changes —
byte-identical verification behaviour to 0.3.0.

### Notes

- 0.3.0 reached npm via a manual bootstrap publish (`--provenance=false`,
  because OIDC only works from CI) and was never tagged in git. 0.3.1 is
  the first release cut by `release.yml` end-to-end, and therefore the
  first with a provenance attestation.
- First publish to PyPI; the `gbverify` project did not exist there before
  this release, so 0.3.0 has no PyPI counterpart and the two registries
  are aligned from 0.3.1 onward.
- Version bumped in `cli-node/package.json`, `cli-python/pyproject.toml`,
  `cli-node/bin/gbverify.js`, and `cli-python/gbverify.py`.

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
