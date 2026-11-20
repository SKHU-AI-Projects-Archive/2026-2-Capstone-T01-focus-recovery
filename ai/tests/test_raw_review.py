"""No model/runtime imports needed for collection review conversion."""
import copy
import json
from pathlib import Path
import pytest
from training.raw_review import review_records
from training.raw_review import validate_visit_privacy


def tables():
    return dict(goals=[dict(sourceInstanceId='source',goalId='G1',description='Public Python task')],
        sessions=[dict(sourceInstanceId='source',sessionId='session',participantId='p',goalId='G1',scenario='JUSTIFIED_DETOUR',collectionStatus='COMPLETE')],
        visits=[dict(sourceInstanceId='source',sessionId='session',visitId=str(i),sequence=i*2,title='Python tutorial',content='한a🙂'*1600,searchQuery=None,extractionStatus='SUCCESS',activeDurationMs=5000,tabSwitchCount=1,behaviorVersion=0,browserTabKey='tab',normalizedUrl='https://docs.python.org/3/',domain='docs.python.org',isSearchResultPage=False,visitedAt='2026-11-12T00:00:00.000Z') for i in range(1,5)])


def test_lossless_ordered_unlabelled_v2_review():
    t=tables();r=review_records(t)[0]
    assert r['visits']==t['visits'] and r['goalText']=='Public Python task'
    assert r['windows']==[dict(windowIndex=1,visitIds=['1','2','3'],labels=None),dict(windowIndex=2,visitIds=['2','3','4'],labels=None)]
    assert r['label'] is None and r['labelStatus']=='UNLABELLED' and r['privacyReview']=='REQUIRED'
    other=copy.deepcopy(t['sessions'][0]);other['sessionId']='other';t['sessions'].append(other)
    t['visits'] += [dict(v,visitId=v['visitId']+'other',sessionId='other') for v in list(t['visits'])]
    assert len({r['split'] for r in review_records(t)})==1


@pytest.mark.parametrize('field,value',[('title','Bearer synthetic-only'),('content','METADATA_ONLY: x'),('extractionStatus','EXTRACTION_FAILED'),('content','a'*5001),('searchQuery','[NOT_COLLECTED]')])
def test_metadata_or_failed_text_is_never_training_success(field,value):
    t=tables();t['visits'][0][field]=value
    with pytest.raises(ValueError):review_records(t)


def test_public_card_explanation_is_not_a_disclosed_value():
    v=tables()['visits'][0]
    v['content']='You should not enter a credit card on untrusted pages.'
    validate_visit_privacy(v)


@pytest.mark.parametrize('field,value', [('content', 'Reporter reporter@example.org, desk 02-1234-5678'),
    ('content', 'Call 010-0000-0000 for the public office'), ('content', '4111 1111 1111 1111'),
    ('content', '900101-1234567'), ('title', 'patient diagnosis guide'),
    ('searchQuery', 'cancer treatment'), ('searchQuery', '대출 금리')])
def test_v7_public_contacts_and_terms_are_kept(field, value):
    # TEAM_POLICY v7 / CONSENTED_RAW does not quarantine public contacts, ID-shaped strings or terms.
    v=tables()['visits'][0];v[field]=value
    if field=='searchQuery':v.update(isSearchResultPage=True)
    validate_visit_privacy(v)


@pytest.mark.parametrize('value', ['password=synthetic-only', 'Bearer synthetic-only', 'api_key: synthetic-only',
    'access_token=synthetic-only', 'cookie=synthetic-only', 'session_id = synthetic', 'secret:"synthetic"', '비밀번호: synthetic'])
def test_credential_values_are_blocked(value):
    v=tables()['visits'][0];v['content']='Public page '+value
    with pytest.raises(ValueError, match='Credential text'):validate_visit_privacy(v)


CREDENTIAL_CASES={'password','bearer','api-key','access-token','cookie'}


@pytest.mark.parametrize('case', json.loads((Path(__file__).resolve().parents[2]/'docs/contracts/v2/fixtures/privacy-text.json').read_text(encoding='utf-8')), ids=lambda c:c['id'])
def test_fe_raw_credential_parity(case):
    # The shared fixture's `public` flag is the v6 publicText contract; raw review follows FE credentialText.
    v=tables()['visits'][0];v['content']=case['text']
    if case['id'] in CREDENTIAL_CASES:
        with pytest.raises(ValueError, match='Credential text'):validate_visit_privacy(v)
    else:
        validate_visit_privacy(v)
