#!/usr/bin/env bash
# gbverify smoke tests. Run this in CI on every change.
set -euo pipefail

cd "$(dirname "$0")"

fail() { echo "✗ $1"; exit 1; }
pass() { echo "✓ $1"; }

# Rebuild the sample so the recorded hash always matches the current
# canonicalisation. If either CLI drifts from the source-of-truth
# assembler in Greenbar-Pay, this test will fail.
node sample/build_sample.js > /dev/null

# Test 1: valid packet passes both CLIs.
node cli-node/bin/gbverify.js sample/packet.json > /dev/null
pass "node: valid packet -> exit 0"
python3 cli-python/gbverify.py sample/packet.json > /dev/null
pass "python: valid packet -> exit 0"

# Test 2: cross-language hash equivalence.
NH=$(node cli-node/bin/gbverify.js --json sample/packet.json | \
     python3 -c "import json,sys;print(json.load(sys.stdin)['manifest']['computedManifestHash'])")
PH=$(python3 cli-python/gbverify.py --json sample/packet.json | \
     python3 -c "import json,sys;print(json.load(sys.stdin)['manifest']['computedManifestHash'])")
[ "$NH" = "$PH" ] || fail "cross-lang hash mismatch: node=$NH python=$PH"
pass "node & python compute the same hash: $NH"

# Test 3: tampered packet is rejected by both.
python3 -c "
import json
p=json.load(open('sample/packet.json'))
p['gbEvidencePacket']['manifest']['extractedInvoice']['total']='99999.99'
json.dump(p,open('sample/packet-tampered.json','w'))
"
if node cli-node/bin/gbverify.js sample/packet-tampered.json > /dev/null 2>&1; then
  fail "node accepted tampered packet"
fi
pass "node: tampered packet -> exit 1"
if python3 cli-python/gbverify.py sample/packet-tampered.json > /dev/null 2>&1; then
  fail "python accepted tampered packet"
fi
pass "python: tampered packet -> exit 1"
rm -f sample/packet-tampered.json

# Test 4: unknown schemaVersion is refused (forward-compat guard).
python3 -c "
import json
p=json.load(open('sample/packet.json'))
p['gbEvidencePacket']['manifest']['schemaVersion']='evidence.v9-imaginary'
json.dump(p,open('sample/packet-vfuture.json','w'))
"
if node cli-node/bin/gbverify.js sample/packet-vfuture.json > /dev/null 2>&1; then
  fail "node accepted unknown schemaVersion"
fi
pass "node: unknown schemaVersion -> refused"
if python3 cli-python/gbverify.py sample/packet-vfuture.json > /dev/null 2>&1; then
  fail "python accepted unknown schemaVersion"
fi
pass "python: unknown schemaVersion -> refused"
rm -f sample/packet-vfuture.json

# Test 5: stdin.
cat sample/packet.json | node cli-node/bin/gbverify.js - > /dev/null
pass "node: stdin -> ok"
cat sample/packet.json | python3 cli-python/gbverify.py - > /dev/null
pass "python: stdin -> ok"

# Test 6: --document mismatch (exit 3).
echo "not the real invoice" > sample/fake.pdf
set +e
node cli-node/bin/gbverify.js --document sample/fake.pdf sample/packet.json > /dev/null 2>&1
NC=$?
python3 cli-python/gbverify.py --document sample/fake.pdf sample/packet.json > /dev/null 2>&1
PC=$?
set -e
[ "$NC" = "3" ] || fail "node --document mismatch should exit 3, got $NC"
[ "$PC" = "3" ] || fail "python --document mismatch should exit 3, got $PC"
pass "node & python: --document mismatch -> exit 3"
rm -f sample/fake.pdf

echo ""
echo "All tests passed."
