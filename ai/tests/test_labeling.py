"""#126 blind labelling core: tasks hide outcome fields, contract-exact labels, consensus, kappa."""
import copy
import json

import pytest

from training import labeling as L
from training.raw_review import review_records

NOW = '2026-11-18T00:00:00.000Z'


def records(sessions=(('s1', 'G1', 'GOAL_MAINTENANCE'),), visits=5):
    goals = [dict(sourceInstanceId='src', goalId=g, description='Public Python task ' + g)
             for g in sorted({s[1] for s in sessions})]
    t = dict(goals=goals, sessions=[], visits=[])
    for sid, goal, scenario in sessions:
        t['sessions'].append(dict(sourceInstanceId='src', sessionId=sid, participantId='participant-secret',
                                  goalId=goal, scenario=scenario, collectionStatus='COMPLETE'))
        t['visits'] += [dict(sourceInstanceId='src', sessionId=sid, visitId=f'{sid}-v{i}', sequence=i,
                             title=f'Page {i}', content='Python tutorial body text. ' * 4, searchQuery=None,
                             extractionStatus='SUCCESS', activeDurationMs=5000 * i, tabSwitchCount=0,
                             behaviorVersion=0, browserTabKey='tab', normalizedUrl='https://docs.python.org/3/',
                             domain='docs.python.org', isSearchResultPage=False,
                             visitedAt='2026-11-12T00:00:00.000Z') for i in range(1, visits + 1)]
    return review_records(t)


def test_tasks_are_blind_and_cover_pages_and_windows():
    tasks, targets = L.build_tasks(records(), 'R1')
    assert sum(t['targetType'] == 'PAGE_VISIT' for t in tasks) == 5
    assert sum(t['targetType'] == 'WINDOW' for t in tasks) == 3
    text = json.dumps(tasks)
    for hidden in ('GOAL_MAINTENANCE', 'participant-secret', 'scenario', 's1-v1', 'sessionId', 'split'):
        assert hidden not in text
    page = next(t for t in tasks if t['targetType'] == 'PAGE_VISIT' and t['position'] == 3)
    assert 'activeDurationMs' not in json.dumps(page)
    assert [p['title'] for p in page['priorContext']] == ['Page 1', 'Page 2']
    window = next(t for t in tasks if t['targetType'] == 'WINDOW')
    assert all('activeDurationMs' in p for p in window['pages'])
    assert set(targets.values()) >= {('PAGE_VISIT', 's1-v1')}


def test_no_prior_context_option_and_rater_specific_order():
    r = records()
    tasks, _ = L.build_tasks(r, 'R1', page_context='none')
    assert all(t['priorContext'] == [] for t in tasks if t['targetType'] == 'PAGE_VISIT')
    a, _ = L.build_tasks(r, 'R1', salt=b'x')
    b, _ = L.build_tasks(r, 'R2', salt=b'x')
    assert sorted(t['taskId'] for t in a) == sorted(t['taskId'] for t in b)
    with pytest.raises(ValueError):
        L.build_tasks(r, 'bad rater!')


def test_hidden_fields_are_rejected():
    with pytest.raises(ValueError):
        L.assert_blind(dict(taskId='x', scenarioType='CLEAR_DRIFT'))
    with pytest.raises(ValueError):
        L.assert_blind(dict(taskId='x', pages=[dict(finalState='DRIFT')]))


def test_pilot_excludes_test_split_and_is_stratified():
    sessions = [(f's{i}', f'G{i}', sc) for i, sc in enumerate(
        ['GOAL_MAINTENANCE', 'JUSTIFIED_DETOUR', 'GRADUAL_DRIFT', 'CLEAR_DRIFT'] * 6)]
    r = records(sessions, visits=10)
    chosen = L.select_pilot(r)
    test_windows = {L.window_id(w['visitIds']) for x in r if x['split'] == 'test' for w in x['windows']}
    assert chosen and not chosen & test_windows and len(chosen) <= 20
    tasks, _ = L.build_tasks(r, 'R1', window_ids=chosen)
    assert sum(t['targetType'] == 'WINDOW' for t in tasks) == len(chosen)


def vote(kind, key, rater, label):
    return L.make_annotation(kind, key, rater, label, '목표와의 관계 요약', NOW)


def test_annotation_contract_and_rationale_rules():
    a = vote('PAGE_VISIT', 'v1', 'R1', 'DIRECT')
    assert set(a) == L.ANNOTATION_FIELDS and a['phase'] == 'INDEPENDENT' and a['labelGuideVersion'] == 'v0.1'
    for bad in [dict(a, label='NORMAL'), dict(a, finalState='DRIFT'), dict(a, raterId=None),
                dict(a, rationale=''), dict(a, rationale='see https://example.org'),
                dict(a, rationale='mail me@example.org'), dict(a, stateVersion=1)]:
        with pytest.raises(ValueError):
            L.validate_annotation(bad)
    with pytest.raises(ValueError):
        L.make_annotation('WINDOW', 'not-a-uuid', 'R1', 'DRIFT', 'x', NOW)


def test_uniqueness_and_consensus():
    w = L.window_id(['a', 'b', 'c'])
    votes = [vote('PAGE_VISIT', 'v1', r, l) for r, l in [('R1', 'DIRECT'), ('R2', 'DIRECT'), ('R3', 'UNRELATED')]]
    votes += [vote('WINDOW', w, r, l) for r, l in [('R1', 'NORMAL'), ('R2', 'TRANSITION'), ('R3', 'DRIFT')]]
    votes += [vote('PAGE_VISIT', 'v2', 'R1', 'DIRECT')]
    with pytest.raises(ValueError):
        L.check_labels(votes + [vote('PAGE_VISIT', 'v1', 'R1', 'UNRELATED')])
    majority, review, incomplete = L.plan_consensus(votes)
    assert majority[('PAGE_VISIT', 'v1', 'v0.1')][0] == 'DIRECT'
    assert review == [('WINDOW', w, 'v0.1')] and incomplete == [('PAGE_VISIT', 'v2', 'v0.1')]
    out, unresolved, _ = L.build_consensus(votes, [], NOW)
    assert unresolved == [('WINDOW', w, 'v0.1')]
    cons = [a for a in out if a['phase'] == 'CONSENSUS']
    assert len(cons) == 1 and cons[0]['raterId'] is None and len(cons[0]['sourceAnnotationIds']) == 3
    decision = dict(targetType='WINDOW', visitId=None, windowId=w, label='TRANSITION', adjudicationNote='공동 검토 결과 전환')
    out, unresolved, _ = L.build_consensus(votes, [decision], NOW)
    assert not unresolved and sum(a['phase'] == 'CONSENSUS' for a in out) == 2
    with pytest.raises(ValueError):
        L.build_consensus(votes, [dict(decision, label='DIRECT')], NOW)


def test_consensus_must_cite_same_target():
    a, b = vote('PAGE_VISIT', 'v1', 'R1', 'DIRECT'), vote('PAGE_VISIT', 'v2', 'R1', 'DIRECT')
    c = dict(copy.deepcopy(a), annotationId='00000000-0000-4000-8000-000000000001', raterId=None,
             phase='CONSENSUS', sourceAnnotationIds=[b['annotationId']])
    with pytest.raises(ValueError):
        L.check_labels([a, b, c])


def test_fleiss_kappa_known_values():
    assert L.fleiss_kappa([['A', 'A', 'A'], ['B', 'B', 'B']], ['A', 'B']) == pytest.approx(1.0)
    assert L.fleiss_kappa([['A', 'A', 'A']] * 3, ['A', 'B']) is None  # all one category: undefined
    assert L.fleiss_kappa([], ['A']) is None
    # Fleiss (1971)-style hand check: 2 items, 3 raters
    k = L.fleiss_kappa([['A', 'A', 'B'], ['B', 'B', 'B']], ['A', 'B'])
    assert k == pytest.approx(((1 / 3 + 1) / 2 - (1 / 3) ** 2 - (2 / 3) ** 2) / (1 - (1 / 3) ** 2 - (2 / 3) ** 2))


def test_kappa_report_separates_unjudgeable():
    votes = [vote('PAGE_VISIT', 'v1', r, 'DIRECT') for r in ('R1', 'R2', 'R3')]
    votes += [vote('PAGE_VISIT', 'v2', r, l) for r, l in [('R1', 'UNRELATED'), ('R2', 'UNRELATED'), ('R3', 'UNJUDGEABLE')]]
    rep = L.kappa_report(votes)['PAGE_VISIT']
    assert rep['items'] == 2 and rep['judgedItems'] == 1 and rep['unjudgeableVotes'] == 1
    assert rep['kappa3'] is None and rep['kappa4'] is not None


@pytest.mark.parametrize('labels,durations,expected', [
    (['UNRELATED', 'UNRELATED', 'DIRECT'], [5000, 5000, 5000], 'NORMAL'),
    (['DIRECT', 'DIRECT', 'UNRELATED'], [5000, 5000, 5000], 'NORMAL'),
    (['DIRECT', 'DIRECT', 'UNRELATED'], [5000, 5000, 300000], 'DRIFT'),
    (['DIRECT', 'UNRELATED', 'UNRELATED'], [5000, 5000, 5000], 'TRANSITION'),
    (['DIRECT', 'UNRELATED', 'UNRELATED'], [5000, 300000, 5000], 'DRIFT'),
    (['UNRELATED', 'UNRELATED', 'UNRELATED'], [5000, 5000, 5000], 'DRIFT'),
    (['JUSTIFIED_DETOUR', 'UNRELATED', 'JUSTIFIED_DETOUR'], [5000, 900000, 5000], 'NORMAL'),
    (['DIRECT', 'UNJUDGEABLE', 'DIRECT'], [5000, 5000, 5000], None),
])
def test_derived_rule_state_matches_be_suffix_rule(labels, durations, expected):
    assert L.derived_rule_state(labels, durations) == expected


def test_derived_states_need_consensus_for_every_page():
    r = records(visits=3)
    ids = r[0]['windows'][0]['visitIds']
    cons = [dict(vote('PAGE_VISIT', i, 'R1', 'DIRECT'), phase='CONSENSUS', raterId=None) for i in ids[:2]]
    assert L.derived_states(r, cons) == {L.window_id(ids): None}
    cons.append(dict(vote('PAGE_VISIT', ids[2], 'R1', 'UNRELATED'), phase='CONSENSUS', raterId=None))
    assert L.derived_states(r, cons) == {L.window_id(ids): 'NORMAL'}
