# gbverify

**Verify the integrity of a Greenbar evidence packet in one command.**

`gbverify` is a small, dependency-free, MIT-licensed tool that recomputes the SHA-256 manifest hash printed on every Greenbar evidence-packet PDF and reports whether it matches the record. It runs entirely on your machine — no network call, no Greenbar account.

If the hash matches, you have cryptographic evidence that the AI-assisted review record on the accompanying PDF is bit-for-bit identical to the record sealed at approval time in Greenbar's database. If it doesn't match, the packet was modified after sealing.

`gbverify` isn't tied to one Greenbar product. It verifies any packet whose `schemaVersion` it recognizes (currently `evidence.v2` — see "Schema versioning" below), regardless of which Greenbar tool sealed it.

## Install

```
npm install -g @greenbarsystemsllc/gbverify   # Node ≥ 18
pipx install gbverify                         # Python ≥ 3.8
```

Or run it once without installing:

```
npx @greenbarsystemsllc/gbverify packet.json
```

## Use

```
$ gbverify packet.json
✓  manifest hash valid
   computed: d7096a4ba450756b3f251b34c83ddada35e5e22f2fe7c3c1a0f676e2686b08f2
   recorded: d7096a4ba450756b3f251b34c83ddada35e5e22f2fe7c3c1a0f676e2686b08f2
   schema:   evidence.v2
```

Also verify the source PDF the AI extracted from:

```
$ gbverify --document invoice.pdf packet.json
✓  manifest hash valid
✓  source document hash matches
```

Machine-readable output:

```
$ gbverify --json packet.json
{"manifest":{"ok":true,"computedManifestHash":"d709…","recordedManifestHash":"d709…", …}}
```

## Try it

`sample/packet.json` is a real (synthetic) evidence packet. `sample/tampered.json` is the same packet with `extractedInvoice.total` changed after sealing — everything else, including the recorded `manifestHash`, is untouched:

```
$ gbverify sample/packet.json
✓  manifest hash valid
   computed: d7096a4ba450756b3f251b34c83ddada35e5e22f2fe7c3c1a0f676e2686b08f2
   recorded: d7096a4ba450756b3f251b34c83ddada35e5e22f2fe7c3c1a0f676e2686b08f2
   schema:   evidence.v2

$ gbverify sample/tampered.json
✗  manifest hash INVALID
   computed: 0468a89c02135b62561ba36bdf6cc31016783a278ceddc4b4aa0acc972cd1bdb
   recorded: d7096a4ba450756b3f251b34c83ddada35e5e22f2fe7c3c1a0f676e2686b08f2
   schema:   evidence.v2

Problems:
  - manifestHash mismatch
```

Exit code is `0` for the first, `1` for the second — the recorded hash never changes, only what it's checked against.

## What a passing verification proves

- **The record is untampered.** The invoice, line items, AI briefing card, deterministic risk score inputs, validation findings, approver attestation, and any blocking-finding override were bit-for-bit identical to what was sealed at approval time.
- **The source PDF is the one the AI reviewed.** With `--document`, the SHA-256 of the file on disk matches the source-document hash recorded in the packet at ingest time.

## What it does not prove

- Whether the approver's judgment was correct.
- Whether the vendor is legitimate.
- Whether the AI's extraction was accurate.

These are review questions. The packet is the evidence you use to ask them, not the answer.

## How the hash is computed

The manifest hash is a SHA-256 over the manifest JSON, serialized with recursively sorted object keys and no incidental whitespace (canonical JSON). The current source-of-truth implementation of this algorithm lives at [`src/lib/evidence/assemble.ts`](https://github.com/GreenbarSystems/Greenbar-Pay/blob/main/src/lib/evidence/assemble.ts) in the Greenbar-Pay repository. `test.sh` checks that gbverify's own Node and Python implementations agree with each other on every change; it does not check them against a live copy of `assemble.ts`. Today, the two repos stay in sync by convention, not by an automated cross-repo test.

You do not need this tool to verify — a five-line Python script or a short shell pipeline will produce the same hash:

```python
import json, hashlib
p = json.load(open("packet.json"))["gbEvidencePacket"]
s = json.dumps(p["manifest"], sort_keys=True, ensure_ascii=False,
               separators=(",", ":"))
assert hashlib.sha256(s.encode("utf-8")).hexdigest() == p["manifestHash"]
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0    | Hash valid (and document hash matches if `--document` was given) |
| 1    | Manifest hash INVALID — packet modified after sealing |
| 2    | Usage error / unreadable input |
| 3    | `--document` mismatch (manifest was valid but the PDF is not the sealed one) |

## Schema versioning

`gbverify` refuses to verify a packet with an unknown `schemaVersion`. This prevents silent mis-hashing when Greenbar changes the canonical-JSON contract. If you receive a packet with a newer schema, upgrade `gbverify`; if you receive one with an older schema, use the matching older `gbverify` release.

Currently supported: `evidence.v2`.

## License

MIT. Contributions welcome. Report canonicalization bugs at [github.com/GreenbarSystems/gbverify/issues](https://github.com/GreenbarSystems/gbverify).
