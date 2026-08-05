#!/usr/bin/env python3
"""gbverify — verify the integrity of a Greenbar Pay evidence packet.

MIT License. Standard library only (Python 3.8+).

Usage:
  gbverify <packet.json>
  gbverify --json <packet.json>
  gbverify --document <invoice.pdf> <packet.json>
  cat packet.json | gbverify -

Exit codes:
  0  hash valid (and document hash matches if --document was given)
  1  hash INVALID — packet modified after sealing
  2  usage error / unreadable input
  3  --document mismatch (manifest was valid, PDF is not the sealed one)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Optional

VERSION = "0.1.0"
SUPPORTED_SCHEMAS = {"evidence.v2"}


# ---------------------------------------------------------------------------
# Canonical-JSON contract.
#
# Must produce byte-for-byte identical output to
# src/lib/evidence/assemble.ts#canonicalJsonStringify in the
# greenbarsystems/Greenbar-Pay repository:
#   - object keys sorted (recursively)
#   - array element order preserved
#   - JSON.stringify default separators: ",", ":" (i.e. no spaces
#     between key/value or between items) — matches Python's
#     separators=(",", ":")
#   - JSON.stringify escapes non-ASCII as \uXXXX only for control
#     chars and surrogate pairs; regular non-ASCII is emitted raw.
#     Python's json.dumps(ensure_ascii=False) matches this.
#   - JS numbers do not distinguish int/float, but here every
#     numeric field in the manifest that could be sensitive is
#     already serialised as a string (see extractedInvoice.subtotal
#     etc. in assemble.ts). Integers like riskScore and page counts
#     come out the same either way.
# ---------------------------------------------------------------------------
def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def unwrap(parsed: Any) -> Any:
    if isinstance(parsed, dict) and "gbEvidencePacket" in parsed:
        return parsed["gbEvidencePacket"]
    return parsed


def verify(packet: Any) -> dict:
    problems = []
    if not isinstance(packet, dict):
        return {"ok": False, "problems": ["packet is not an object"]}

    manifest = packet.get("manifest")
    manifest_hash = packet.get("manifestHash")
    source_doc_hash = packet.get("sourceDocumentHash")

    if not isinstance(manifest, dict):
        problems.append("manifest is missing")
    if not (isinstance(manifest_hash, str) and len(manifest_hash) == 64
            and all(c in "0123456789abcdef" for c in manifest_hash)):
        problems.append("manifestHash is missing or not a 64-hex SHA-256")
    if isinstance(manifest, dict):
        schema = manifest.get("schemaVersion")
        if schema not in SUPPORTED_SCHEMAS:
            problems.append(
                f"unsupported schemaVersion {schema!r} — this gbverify "
                f"understands: {sorted(SUPPORTED_SCHEMAS)}"
            )
    if problems:
        return {"ok": False, "problems": problems}

    computed = sha256_hex(canonical_json(manifest).encode("utf-8"))
    hash_ok = computed == manifest_hash

    manifest_doc_hash = (manifest.get("originalDocument") or {}).get("contentHash")
    envelope_ok = (
        not source_doc_hash
        or not manifest_doc_hash
        or source_doc_hash == manifest_doc_hash
    )

    problems = []
    if not hash_ok:
        problems.append("manifestHash mismatch")
    if not envelope_ok:
        problems.append(
            "envelope sourceDocumentHash != manifest.originalDocument.contentHash"
        )

    return {
        "ok": hash_ok and envelope_ok,
        "hashMatches": hash_ok,
        "envelopeMatches": envelope_ok,
        "computedManifestHash": computed,
        "recordedManifestHash": manifest_hash,
        "manifestDocHash": manifest_doc_hash,
        "envelopeSourceDocumentHash": source_doc_hash,
        "schemaVersion": manifest.get("schemaVersion"),
        "problems": problems,
    }


def verify_document(packet: dict, doc_path: str) -> dict:
    expected = ((packet.get("manifest") or {}).get("originalDocument") or {}).get(
        "contentHash"
    )
    if not expected:
        return {
            "ok": False,
            "problems": [
                "packet has no originalDocument.contentHash to compare against"
            ],
        }
    actual = sha256_file(doc_path)
    return {
        "ok": expected == actual,
        "expected": expected,
        "actual": actual,
        "docPath": os.path.abspath(doc_path),
        "problems": [] if expected == actual else ["document hash mismatch"],
    }


def render(result: dict, doc_result: Optional[dict], json_out: bool) -> None:
    if json_out:
        print(json.dumps({"manifest": result, "document": doc_result}, indent=2))
        return

    use_color = sys.stdout.isatty()
    def g(s): return f"\x1b[32m{s}\x1b[0m" if use_color else s
    def r(s): return f"\x1b[31m{s}\x1b[0m" if use_color else s
    def d(s): return f"\x1b[2m{s}\x1b[0m" if use_color else s

    print((g("✓") if result["ok"] else r("✗")) + "  manifest hash "
          + ("valid" if result["ok"] else "INVALID"))
    print(d(f"   computed: {result['computedManifestHash']}"))
    print(d(f"   recorded: {result['recordedManifestHash']}"))
    print(d(f"   schema:   {result['schemaVersion']}"))

    if doc_result is not None:
        print((g("✓") if doc_result["ok"] else r("✗"))
              + "  source document hash "
              + ("matches" if doc_result["ok"] else "MISMATCH"))
        print(d(f"   expected: {doc_result['expected']}"))
        print(d(f"   actual:   {doc_result['actual']}"))
        print(d(f"   file:     {doc_result['docPath']}"))

    problems = list(result.get("problems") or [])
    if doc_result:
        problems.extend(doc_result.get("problems") or [])
    if problems:
        print("\nProblems:")
        for p in problems:
            print(f"  - {p}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="gbverify", add_help=False)
    ap.add_argument("packet", nargs="?", help="path to packet.json, or - for stdin")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--document", "-d", metavar="FILE",
                    help="also verify the source-document hash against FILE")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()

    if args.help or (not args.packet and not args.version):
        print(__doc__.strip())
        sys.exit(0 if args.help else 2)
    if args.version:
        print(VERSION)
        sys.exit(0)

    try:
        if args.packet == "-":
            raw = sys.stdin.read()
        else:
            with open(args.packet, "r", encoding="utf-8") as f:
                raw = f.read()
    except OSError as e:
        print(f"cannot read packet: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"packet is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)

    packet = unwrap(parsed)
    result = verify(packet)

    doc_result = None
    if args.document:
        try:
            doc_result = verify_document(packet, args.document)
        except OSError as e:
            print(f"cannot read document: {e}", file=sys.stderr)
            sys.exit(2)

    render(result, doc_result, args.json)

    if not result["ok"]:
        sys.exit(1)
    if doc_result and not doc_result["ok"]:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
