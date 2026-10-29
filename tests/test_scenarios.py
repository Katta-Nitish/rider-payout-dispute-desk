import json
from pathlib import Path
import app
from sqlalchemy import text

CASES=json.loads((Path(__file__).resolve().parents[1]/'data'/'conversations.json').read_text(encoding='utf-8'))

def test_supplied_scenarios_against_isolated_mock_provider(monkeypatch):
    """Fast deterministic fixture test; not a substitute for the real PaySwift integration eval."""
    ledger=[]
    def getp(rider): return [x.copy() for x in ledger if app.norm_rider(x['rider_id'])==app.norm_rider(rider)]
    def create(rider, amount, reference, key):
        existing=next((x for x in ledger if x['key']==key),None)
        if existing: return {'ok':True,'result':{'payout_id':existing['payout_id'],'status':'already_processed'}}
        item={'payout_id':f'p{len(ledger)+1}','rider_id':rider,'amount':amount,'reference':reference,'created_at':'2026-09-23T10:00:00+05:30','key':key}
        ledger.append(item); return {'ok':True,'result':item}
    monkeypatch.setattr(app,'get_payswift',getp)
    monkeypatch.setattr(app,'create_payswift_payment',create)
    for case in CASES:
        with app.engine.begin() as db:
            for table in ['processed_messages','trace_steps','pending_ops','conversations']:
                db.execute(text('DELETE FROM '+table))
        ledger.clear(); replies=[]
        for turn in case['turns']:
            if turn['from']=='rider':
                payload=app.MessageIn(message_id=turn['message_id'],rider_id=case['rider_id'],text=turn['text'],received_at=turn['received_at'])
                replies.append(app.messages(payload)['reply'])
        expected=case['expected']; paid=sum(int(x['amount']) for x in ledger if app.norm_rider(x['rider_id'])==app.norm_rider(case['rider_id']))
        pending=app.pending(); approval=sum(int(x['amount'] or 0) for x in pending if x['type']=='approval') or None
        if 'one_of' in expected:
            assert any(paid==o.get('payout',0) and (approval or 0)==(o.get('approval') or 0) for o in expected['one_of']),case['scenario']
        else:
            assert paid==expected.get('payout',0),case['scenario']
            if 'approval' in expected: assert approval==expected['approval'],case['scenario']
        joined=' '.join(replies).lower()
        assert all(str(x).lower() in joined for x in expected.get('reply_mentions',[])),case['scenario']
