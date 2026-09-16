#!/usr/bin/env bash
# Refresh the demo account on a deployed FinMate API.
#   usage: bash refresh-demo.sh https://your-api.onrender.com
set -euo pipefail
API="${1:?pass your Render API base URL}"

echo "1. Backend version check"
if curl -s -m 30 "$API/" | grep -q "Safe-to-Spend"; then
  echo "   OK - backend has the Tier 1 code"
else
  echo "   STALE - this backend predates Tier 1. Redeploy it first, then rerun."
  exit 1
fi

echo "2. Signing in as the demo account"
TOKEN=$(curl -s -m 30 -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@finmate.ai","password":"demo1234"}' \
  | python -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
[ -n "$TOKEN" ] || { echo "   login failed"; exit 1; }
echo "   OK"

echo "3. Regenerating sample data anchored to today"
curl -s -m 60 -X POST "$API/api/profile/load-sample?reset=true" \
  -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json;print('  ',json.load(sys.stdin).get('message'))"

echo "4. Verifying the current month is populated"
curl -s -m 60 "$API/api/twin/snapshot" -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json;d=json.load(sys.stdin);print('   income',d['total_income_month'],'expense',d['total_expense_month'],'cash flow',d['cash_flow'])"
curl -s -m 60 "$API/api/forecast/budget" -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json;print('   budget comparison rows:',len(json.load(sys.stdin)))"
