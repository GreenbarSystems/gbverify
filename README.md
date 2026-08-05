# gbverify

**Verify the integrity of a Greenbar Pay evidence packet in one command.**

`gbverify` is a small, dependency-free, MIT-licensed tool that recomputes the SHA-256 manifest hash printed on every Greenbar Pay evidence-packet PDF and reports whether it matches the record. It runs entirely on your machine — no network call, no Greenbar account.

If the hash matches, you have cryptographic evidence that the AI-assisted review record on the accompanying PDF is bit-for-bit identical to the record sealed at approval time in Greenbar Pay's database. If it doesn't match, the packet was modified after sealing.

## Install

```
npm install -g @greenbarsystems/gbverify   # Node ≥ 18
pipx install gbverify                      # Python ≥ 3.8
brew install gbverify                      # macOS, Linux
```

Or run it once without installing:

```
npx @greenbarsystems/gbverify packet.json
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

## What a passing verification proves

- **The record is untampered.** The invoice, line items, AI briefing card, deterministic risk score inputs, validation findings, approver attestation, and any blocking-finding override were bit-for-bit identical to what Greenbar Pay sealed at approval time.
- **The source PDF is the one the AI reviewed.** With `--document`, the SHA-256 of the file on disk matches the source-document hash recorded in the packet at ingest time.

## What it does not prove

- Whether the approver's judgment was correct.
- Whether the vendor is legitimate.
- Whether the AI's extraction was accurate.

These are review questions. The packet is the evidence you use to ask them, not the answer.

## How the hash is computed

The manifest hash is a SHA-256 over the manifest JSON, serialised with recursively sorted object keys and no incidental whitespace (canonical JSON). This is the same algorithm implemented at [`src/lib/evidence/assemble.ts`](https://github.com/greenbarsystems/Greenbar-Pay/blob/main/src/lib/evidence/assemble.ts) in the Greenbar Pay repository.

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

MIT. Contributions welcome. Report canonicalisation bugs at [github.com/greenbarsystems/gbverify/issues](https://github.com/greenbarsystems/gbverify).
