"""Black-box conversation evaluator. Uses only /messages, /ops/pending and PaySwift APIs."""
import json, sys, time, requests
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'data'/'conversations.json').read_text(encoding='utf-8'))

def payouts(base, rider):
    try:
        r=requests.get(base.rstrip('/')+'/v1/payouts',params={'rider_id':rider},timeout=4)
        if not r.ok: return None
        j=r.json()
        return j if isinstance(j,list) else j.get('payouts',j.get('items',[]))
    except Exception: return None

def pending(base):
    try:
        r=requests.get(base.rstrip('/')+'/ops/pending',timeout=4)
        return r.json() if r.ok else []
    except Exception: return []

def amount_total(items):
    return sum(int(x.get('amount') or 0) for x in items)
def main():
    if len(sys.argv)!=2:
        print('Usage: python evals/run.py http://localhost:8000'); return 2
    base=sys.argv[1].rstrip('/'); provider=base.replace(':8000',':8081')
    try:
        requests.get(base+'/health',timeout=3).raise_for_status()
    except Exception as e:
        print(f'Service not ready at {base}: {e}'); return 2
    results=[]
    for case in CASES:
        rider=case['rider_id']; expected=case['expected']; before=payouts(provider,rider); pending_before=pending(base)
        before_ids={x.get('payout_id') or x.get('id') for x in (before or [])}
        before_pending_ids={x.get('id') for x in pending_before}
        messages=[t for t in case['turns'] if t.get('from')=='rider']
        replies=[]
        for turn in messages:
            payload={'message_id':turn['message_id'],'rider_id':rider,'text':turn['text'],'received_at':turn['received_at']}
            try:
                rr=requests.post(base+'/messages',json=payload,timeout=10); rr.raise_for_status(); replies.append(rr.json().get('reply',''))
            except Exception as e: replies.append(f'ERROR: {e}')
        after=payouts(provider,rider); pending_after=pending(base)
        new=[x for x in (after or []) if (x.get('payout_id') or x.get('id')) not in before_ids]
        new_pending=[x for x in pending_after if x.get('id') not in before_pending_ids and x.get('rider_id')==rider]
        paid=sum(int(x.get('amount') or 0) for x in new)
        approval=sum(int(x.get('amount') or 0) for x in new_pending if x.get('type')=='approval') or None
        payout_expected=expected.get('payout',0)
        payout_ok=paid==payout_expected
        if 'one_of' in expected:
            payout_ok=any(paid==v.get('payout',0) and (approval or 0)==(v.get('approval') or 0) for v in expected['one_of'])
        if 'approval' in expected and 'one_of' not in expected:
            approval_ok=approval==expected['approval']
        else: approval_ok=True
        mentions=expected.get('reply_mentions',[])
        joined=' '.join(replies).lower()
        mentions_ok=all(str(m).lower() in joined for m in mentions)
        escalation_ok=True
        if expected.get('escalation')=='no':
            escalation_ok=not any(x.get('type')=='escalation' for x in new_pending)
        # Empty reply_mentions means no lexical requirement.
        ok=payout_ok and approval_ok and mentions_ok and escalation_ok
        results.append({'scenario':case['scenario'],'pass':ok,'expected_payout':payout_expected,'observed_payout':paid,'expected_approval':expected.get('approval'),'observed_approval':approval,'mentions_ok':mentions_ok,'escalation_ok':escalation_ok,'last_reply':replies[-1] if replies else ''})
        print(('PASS' if ok else 'FAIL')+f" | {case['scenario']} | paid={paid}, approval={approval}")
    passed=sum(r['pass'] for r in results)
    print(f'\nRESULT: {passed}/{len(results)} scenarios passed ({100*passed/len(results):.1f}%). This is an observed run, not a guarantee of correctness.')
    (ROOT/'evals'/'last-report.json').write_text(json.dumps({'passed':passed,'total':len(results),'results':results},indent=2,ensure_ascii=False))
    return 0 if passed==len(results) else 1
if __name__=='__main__': raise SystemExit(main())
