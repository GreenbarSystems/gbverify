# Releasing gbverify

`gbverify` publishes to two registries on every `v*.*.*` tag: **npm**
(`@greenbarsystems/gbverify`) and **PyPI** (`gbverify`). Both use
**OIDC trusted publishing** — no long-lived tokens are stored as
GitHub secrets. This document is the one-time setup and the ongoing
release procedure.

---

## Why trusted publishing (and not stored tokens)

`gbverify` is a security-adjacent tool: auditors verify the packets
Greenbar produces by running its code. Its trust story rests on
"you can inspect and rebuild this yourself." A stored npm token or
PyPI API key hidden in GitHub Secrets weakens that story — a
compromised token, or an insider with `Actions: write`, could
publish a malicious version. Trusted publishing binds each release
to a specific workflow file, in a specific repo, on a specific ref
(the tag), verified by GitHub's OIDC provider directly.

Each release published this way carries:

- **npm provenance** — a signed attestation visible on npmjs.com
  (the little checkmark) that says "this tarball came from this
  commit in this workflow." Users can `npm audit signatures` to
  verify.
- **PyPI attestations** — analogous cryptographic provenance shown
  on the PyPI project page.

## One-time setup

### npm side

1. Sign in to <https://www.npmjs.com> as an org owner.
2. Create the org `@greenbarsystems` if it doesn't exist:
   <https://www.npmjs.com/org/create>.
   Choose the **free** tier — public packages only, which is what we
   want.
3. Navigate to the org → **Settings** → **Trusted publishing** →
   **Add trusted publisher**.
4. Enter:
   - Publisher: **GitHub Actions**
   - Organization/user: `GreenbarSystems`
   - Repository: `gbverify`
   - Workflow filename: `release.yml`
   - Environment name: *(leave blank)*
5. Save.

### PyPI side

1. Sign in to <https://pypi.org>.
2. Go to **Your projects** → **Publishing**  →  **Add a new
   pending publisher** (this variant is used for a project that
   doesn't yet exist on PyPI; PyPI reserves the name and links it
   to the workflow at the same time).
3. Enter:
   - Project name: `gbverify`
   - Owner: `GreenbarSystems`
   - Repository name: `gbverify`
   - Workflow name: `release.yml`
   - Environment name: *(leave blank)*
4. Save.

If `gbverify` already exists on PyPI (name-squat or previous release),
use **Manage → Publishing** on the project page instead, and add a
regular trusted publisher rule with the same fields.

---

## Cutting a release

```bash
# 1. Everything green on main
./test.sh

# 2. Bump the version in three files, atomically
#    (a helper script would be nice future work; low priority)
$EDITOR cli-node/package.json     # "version": "X.Y.Z"
$EDITOR cli-python/pyproject.toml # version = "X.Y.Z"
$EDITOR cli-node/bin/gbverify.js  # const VERSION = "X.Y.Z";
$EDITOR cli-python/gbverify.py    # VERSION = "X.Y.Z"

# 3. Regenerate the sample if any hash-relevant path changed
#    (usually no — sample is stable across metadata releases)
node sample/build_sample.js
python3 pdf/render_pdf.py
./test.sh   # must still pass

# 4. Commit and tag
git commit -am "vX.Y.Z: <one-line summary>"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

That's it. GitHub Actions picks up the tag push and:

1. Runs `./test.sh` in a clean runner.
2. Publishes `@greenbarsystems/gbverify@X.Y.Z` to npm with provenance.
3. Publishes `gbverify==X.Y.Z` to PyPI with attestations.
4. Creates a GitHub Release with the sample-packet's manifest hash
   in the notes and the sample packet + PDF as release assets.

---

## Rolling back a bad release

If a release ships with a bug that changes the canonicalization
contract by mistake, **do not `npm unpublish` or PyPI-delete**. Both
registries either forbid it (npm on packages >72h old with any
downloads) or leave the version number permanently reserved (PyPI).

Instead:

1. Immediately publish `vX.Y.(Z+1)` reverting the offending commit.
2. Mark the bad version deprecated:
   ```
   npm deprecate @greenbarsystems/gbverify@X.Y.Z \
     "canonicalization regression; upgrade to X.Y.(Z+1)"
   ```
3. Update Greenbar-Pay's `vendor/gbverify` submodule to point at
   the fixed tag.
4. Open a follow-up PR against Greenbar-Pay whose *only* diff is
   the submodule pointer bump, so the drift check exercises the fix
   in isolation.

---

## Auditor sanity check

Any auditor can verify a published version wasn't tampered with:

```
# npm side — verifies the provenance chain to a specific GitHub commit
npm view @greenbarsystems/gbverify@X.Y.Z --json | jq '.dist'
npm audit signatures @greenbarsystems/gbverify@X.Y.Z

# PyPI side — download the wheel and check attestations
pip download gbverify==X.Y.Z --no-deps
# then use pypi-attestations-verify or the sigstore CLI
```

Both should trace back to a commit on `github.com/GreenbarSystems/gbverify`
signed by the `release.yml` workflow.
