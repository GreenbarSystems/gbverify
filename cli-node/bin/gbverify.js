#!/usr/bin/env node
// gbverify — verify the integrity of a Greenbar AP Assurance evidence packet.
// MIT License. Zero runtime dependencies.
//
// Usage:
//   gbverify <packet.json>
//   gbverify --json <packet.json>
//   gbverify --document <invoice.pdf> <packet.json>
//   cat packet.json | gbverify -
//
// Exit codes:
//   0  hash valid (and, if --document was given, source document hash matches)
//   1  hash INVALID — the packet was modified after sealing
//   2  usage error / unreadable input
//   3  --document mismatch (manifest hash was valid but the supplied PDF
//      does not match originalDocument.contentHash)

"use strict";

const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const VERSION = "0.2.0";
const SUPPORTED_SCHEMAS = new Set(["evidence.v2"]);

function usage() {
  process.stderr.write(
    [
      "gbverify " + VERSION + " — Greenbar AP Assurance evidence packet verifier",
      "",
      "Usage:",
      "  gbverify <packet.json>              Verify a packet file",
      "  gbverify --json <packet.json>       Emit machine-readable JSON result",
      "  gbverify --document <file> <pkt>    Also check the source document hash",
      "  gbverify -                          Read packet from stdin",
      "  gbverify --version                  Print version",
      "",
      "Exit: 0 valid | 1 invalid | 2 usage | 3 document mismatch",
      "",
    ].join("\n"),
  );
}

// ---------------------------------------------------------------------------
// Canonical-JSON contract.
//
// This function MUST stay byte-for-byte identical to
// src/lib/evidence/assemble.ts#canonicalJsonStringify in the
// GreenbarSystems/Greenbar-Pay repository. If Greenbar ever changes the
// canonicalisation, they MUST bump manifest.schemaVersion so old
// verifiers refuse to verify new packets rather than silently
// mis-hashing them.
// ---------------------------------------------------------------------------
function canonicalJsonStringify(value) {
  return JSON.stringify(value, (_key, v) => {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const sorted = {};
      for (const k of Object.keys(v).sort()) sorted[k] = v[k];
      return sorted;
    }
    return v;
  });
}

function sha256Hex(buf) {
  return createHash("sha256").update(buf).digest("hex");
}

function sha256File(filePath) {
  return sha256Hex(fs.readFileSync(filePath));
}

function readInput(source) {
  if (source === "-") {
    // stdin
    let data = "";
    const chunks = [];
    const fd = 0;
    const buf = Buffer.alloc(65536);
    let n;
    while ((n = fs.readSync(fd, buf, 0, buf.length, null)) > 0) {
      chunks.push(buf.slice(0, n).toString("utf8"));
    }
    return chunks.join("");
  }
  return fs.readFileSync(source, "utf8");
}

function unwrap(parsed) {
  // Accept either the envelope (`{ gbEvidencePacket: {...} }`) or a raw
  // packet object with `manifest` + `manifestHash` at the top level.
  if (parsed && typeof parsed === "object" && parsed.gbEvidencePacket) {
    return parsed.gbEvidencePacket;
  }
  return parsed;
}

function verify(packet) {
  const problems = [];

  if (!packet || typeof packet !== "object") {
    problems.push("packet is not an object");
    return { ok: false, problems };
  }

  const { manifest, manifestHash, sourceDocumentHash } = packet;

  if (!manifest || typeof manifest !== "object") {
    problems.push("manifest is missing");
  }
  if (typeof manifestHash !== "string" || !/^[0-9a-f]{64}$/.test(manifestHash)) {
    problems.push("manifestHash is missing or not a 64-hex SHA-256");
  }
  if (manifest && !SUPPORTED_SCHEMAS.has(manifest.schemaVersion)) {
    problems.push(
      "unsupported schemaVersion '" +
        manifest.schemaVersion +
        "' — this gbverify build understands: " +
        [...SUPPORTED_SCHEMAS].join(", "),
    );
  }
  if (problems.length) return { ok: false, problems };

  // Recompute and compare.
  const computed = sha256Hex(canonicalJsonStringify(manifest));
  const hashMatches = computed === manifestHash;

  // Cross-check: the manifest's own originalDocument.contentHash should
  // match the packet-level sourceDocumentHash (they're populated from
  // the same source in the assembler; a mismatch means the envelope was
  // edited).
  const manifestDocHash =
    manifest.originalDocument && manifest.originalDocument.contentHash;
  const envelopeMatches =
    !sourceDocumentHash ||
    !manifestDocHash ||
    sourceDocumentHash === manifestDocHash;

  return {
    ok: hashMatches && envelopeMatches,
    hashMatches,
    envelopeMatches,
    computedManifestHash: computed,
    recordedManifestHash: manifestHash,
    manifestDocHash,
    envelopeSourceDocumentHash: sourceDocumentHash,
    schemaVersion: manifest.schemaVersion,
    problems: [
      ...(hashMatches ? [] : ["manifestHash mismatch"]),
      ...(envelopeMatches
        ? []
        : ["envelope sourceDocumentHash != manifest.originalDocument.contentHash"]),
    ],
  };
}

function verifyDocument(packet, docPath) {
  const expected =
    packet.manifest &&
    packet.manifest.originalDocument &&
    packet.manifest.originalDocument.contentHash;
  if (!expected) {
    return {
      ok: false,
      problems: ["packet has no originalDocument.contentHash to compare against"],
    };
  }
  const actual = sha256File(docPath);
  return {
    ok: expected === actual,
    expected,
    actual,
    docPath: path.resolve(docPath),
    problems: expected === actual ? [] : ["document hash mismatch"],
  };
}

function render(result, docResult, jsonOut) {
  if (jsonOut) {
    process.stdout.write(
      JSON.stringify({ manifest: result, document: docResult ?? null }, null, 2) +
        "\n",
    );
    return;
  }
  const green = (s) => "\x1b[32m" + s + "\x1b[0m";
  const red = (s) => "\x1b[31m" + s + "\x1b[0m";
  const dim = (s) => "\x1b[2m" + s + "\x1b[0m";
  const ok = "✓";
  const bad = "✗";

  if (result.ok) {
    process.stdout.write(green(ok) + "  manifest hash valid\n");
  } else {
    process.stdout.write(red(bad) + "  manifest hash INVALID\n");
  }
  process.stdout.write(dim("   computed: " + result.computedManifestHash + "\n"));
  process.stdout.write(dim("   recorded: " + result.recordedManifestHash + "\n"));
  process.stdout.write(dim("   schema:   " + result.schemaVersion + "\n"));

  if (docResult) {
    if (docResult.ok) {
      process.stdout.write(green(ok) + "  source document hash matches\n");
    } else {
      process.stdout.write(red(bad) + "  source document hash MISMATCH\n");
    }
    process.stdout.write(dim("   expected: " + docResult.expected + "\n"));
    process.stdout.write(dim("   actual:   " + docResult.actual + "\n"));
    process.stdout.write(dim("   file:     " + docResult.docPath + "\n"));
  }

  if (result.problems.length || (docResult && docResult.problems.length)) {
    process.stdout.write("\nProblems:\n");
    for (const p of result.problems) process.stdout.write("  - " + p + "\n");
    if (docResult) for (const p of docResult.problems) process.stdout.write("  - " + p + "\n");
  }
}

function main(argv) {
  const args = argv.slice(2);
  if (!args.length || args.includes("-h") || args.includes("--help")) {
    usage();
    process.exit(args.length ? 0 : 2);
  }
  if (args.includes("--version")) {
    process.stdout.write(VERSION + "\n");
    process.exit(0);
  }

  let jsonOut = false;
  let docPath = null;
  const positional = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--json") jsonOut = true;
    else if (a === "--document" || a === "-d") docPath = args[++i];
    else positional.push(a);
  }

  if (positional.length !== 1) {
    usage();
    process.exit(2);
  }

  let raw;
  try {
    raw = readInput(positional[0]);
  } catch (e) {
    process.stderr.write("cannot read packet: " + e.message + "\n");
    process.exit(2);
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    process.stderr.write("packet is not valid JSON: " + e.message + "\n");
    process.exit(2);
  }

  const packet = unwrap(parsed);
  const result = verify(packet);

  let docResult = null;
  if (docPath) {
    try {
      docResult = verifyDocument(packet, docPath);
    } catch (e) {
      process.stderr.write("cannot read document: " + e.message + "\n");
      process.exit(2);
    }
  }

  render(result, docResult, jsonOut);

  if (!result.ok) process.exit(1);
  if (docResult && !docResult.ok) process.exit(3);
  process.exit(0);
}

main(process.argv);
