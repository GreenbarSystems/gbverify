#!/usr/bin/env bash
# gbverify smoke tests. Run this in CI on every change.
set -euo pipefail

cd "$(dirname "$0")"

fail() { echo "✗ $1"; exit 1; }
pass() { echo "✓ $1"; }

# Rebuild the sample so the recorded hash always matches the current
# canonicalization. If either CLI drifts from the source-of-truth
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

# Test 7: canonicalization edge case — negative zero must not diverge.
# JS JSON.stringify(-0) emits "-0" while Python json.dumps(-0.0) emits
# "-0.0" — without normalization the two CLIs disagree. Both sides
# normalize -0 -> 0 before serialization. This fixture would go red if
# either implementation regresses.
#
# Note: we inject -0.0 into the manifest AFTER it was sealed, so the
# recorded hash intentionally no longer matches the new content. Both
# CLIs will exit 1 on this fixture — that's expected. We only care
# that they COMPUTE the same new hash. `set +e` disables pipefail for
# this block so the expected exit-1 doesn't abort the suite.
set +e
python3 -c "
import json
p=json.load(open('sample/packet.json'))
p['gbEvidencePacket']['manifest']['_negzero_fixture']=-0.0
json.dump(p, open('sample/packet-negzero.json','w'), ensure_ascii=False)
"
NZH_N=$(node cli-node/bin/gbverify.js --json sample/packet-negzero.json 2>/dev/null | \
        python3 -c "import json,sys;print(json.load(sys.stdin)['manifest']['computedManifestHash'])")
NZH_P=$(python3 cli-python/gbverify.py --json sample/packet-negzero.json 2>/dev/null | \
        python3 -c "import json,sys;print(json.load(sys.stdin)['manifest']['computedManifestHash'])")
set -e
[ -n "$NZH_N" ] && [ "$NZH_N" = "$NZH_P" ] || fail "cross-lang hash mismatch on -0.0 fixture: node=$NZH_N python=$NZH_P"
pass "node & python agree on -0.0 canonicalization: $NZH_N"
rm -f sample/packet-negzero.json

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
