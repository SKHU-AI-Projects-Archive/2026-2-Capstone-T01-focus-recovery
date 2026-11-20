"""Blind human labelling of v2 training-review records (#126).

Builds rater tasks from `focus-training-review/1` records without scenario, participant,
AI or BE fields, validates `human_labels.jsonl` annotations, plans majority/adjudicated
consensus, computes Fleiss' kappa and the BE suffix rule on human page labels.
Never derives a label from a scenario or a model prediction.
"""
import hashlib
import random
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime

from training.raw_review import sensitive_text

GUIDE_VERSION = 'v0.1'
PAGE_LABELS = ('DIRECT', 'JUSTIFIED_DETOUR', 'UNRELATED', 'UNJUDGEABLE')
WINDOW_LABELS = ('NORMAL', 'TRANSITION', 'DRIFT', 'UNJUDGEABLE')
LABELS = {'PAGE_VISIT': PAGE_LABELS, 'WINDOW': WINDOW_LABELS}
RELATED = {'DIRECT', 'JUSTIFIED_DETOUR'}
LONG_DWELL_MS = 300_000
PAGE_CONTEXTS = ('none', 'prior')
RATER = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
WINDOW_NAMESPACE = uuid.UUID('6f1d7a52-58c4-4f43-9a51-8b4d1d1e1260')
ANNOTATION_FIELDS = {'annotationId', 'targetType', 'visitId', 'windowId', 'stateVersion',
                     'referenceStateVersion', 'raterId', 'label', 'phase', 'sourceAnnotationIds',
                     'labelGuideVersion', 'labeledAt', 'rationale', 'adjudicationNote'}
# Fields a rater must never receive: they would leak the intended outcome or identity.
HIDDEN = re.compile(r'scenario|participant|prediction|finalState|pageResults|semanticRelevance|split|attempt|session', re.I)


def window_id(visit_ids):
    """Stable ID for a raw review window. RAW_ONLY data has no AI windowId or stateVersion."""
    return str(uuid.uuid5(WINDOW_NAMESPACE, '\x1f'.join(visit_ids)))


def _page(v):
    return dict(title=v['title'], content=v['content'], searchQuery=v['searchQuery'],
                isSearchResultPage=v['isSearchResultPage'], domain=v['domain'])


def select_pilot(records, per_scenario=5, seed=126):
    """Pilot windows from non-test goals, stratified by scenario. Scenario is used ONLY to
    sample; it is never sent to raters or stored with labels."""
    pools = defaultdict(list)
    for r in records:
        if r['split'] == 'test':
            continue
        for w in r['windows']:
            pools[r['scenarioType']].append(window_id(w['visitIds']))
    rng = random.Random(seed)
    chosen = set()
    for scenario in sorted(pools):
        pool = sorted(pools[scenario])
        chosen.update(rng.sample(pool, min(per_scenario, len(pool))))
    return chosen


def build_tasks(records, rater_id, page_context='prior', window_ids=None, salt=b''):
    """Return (tasks, targets). tasks are rater-visible; targets map opaque taskId -> label key.

    window_ids restricts to a pilot subset (pages = visits inside those windows).
    Order is shuffled per rater so raters do not share a presentation order.
    """
    if not RATER.match(rater_id):
        raise ValueError('Rater ID must be 1-32 letters, digits, _ or -')
    if page_context not in PAGE_CONTEXTS:
        raise ValueError('page_context must be none or prior')
    tasks, targets = [], {}

    def add(kind, key, body):
        task_id = hashlib.sha256(salt + kind.encode() + b'\x1f' + key.encode()).hexdigest()[:20]
        if task_id in targets:
            raise ValueError('Duplicate label target')
        targets[task_id] = (kind, key)
        tasks.append(dict(taskId=task_id, targetType=kind, **body))

    for r in records:
        if r.get('labelStatus') != 'UNLABELLED' or r.get('schemaVersion') != 'focus-training-review/1':
            raise ValueError('Unlabelled focus-training-review/1 records required')
        visits = {v['visitId']: v for v in r['visits']}
        ordered = r['visits']
        selected = [w for w in r['windows'] if window_ids is None or window_id(w['visitIds']) in window_ids]
        page_ids = ({vid for w in selected for vid in w['visitIds']} if window_ids is not None
                    else set(visits))
        for index, v in enumerate(ordered):
            if v['visitId'] not in page_ids:
                continue
            prior = ([dict(title=p['title'], searchQuery=p['searchQuery']) for p in ordered[:index]]
                     if page_context == 'prior' else [])
            add('PAGE_VISIT', v['visitId'], dict(goalText=r['goalText'], position=index + 1,
                                                 priorContext=prior, page=_page(v)))
        for w in selected:
            pages = [dict(_page(visits[vid]), activeDurationMs=visits[vid]['activeDurationMs'])
                     for vid in w['visitIds']]
            add('WINDOW', window_id(w['visitIds']), dict(goalText=r['goalText'], pages=pages))
    random.Random(hashlib.sha256(salt + rater_id.encode()).digest()).shuffle(tasks)
    tasks.sort(key=lambda t: t['targetType'] != 'PAGE_VISIT')  # pages first, stable shuffle inside
    for t in tasks:
        assert_blind(t)
    return tasks, targets


def assert_blind(task):
    def walk(value, path):
        if isinstance(value, dict):
            for k, v in value.items():
                if HIDDEN.search(k):
                    raise ValueError('Hidden field in rater task: ' + path + k)
                walk(v, path + k + '.')
        elif isinstance(value, list):
            for item in value:
                walk(item, path)
    walk(task, '')


def _timestamp(text):
    if not isinstance(text, str) or not text.endswith('Z'):
        raise ValueError('UTC timestamp required')
    datetime.fromisoformat(text[:-1] + '+00:00')


def validate_rationale(text, required=True):
    if text is None and not required:
        return
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500 or len(text) > 500:
        raise ValueError('Rationale must be 1-500 characters')
    if sensitive_text(text) or re.search(r'https?://|[\w.+-]+@[\w-]+\.[\w.]+', text):
        raise ValueError('Rationale must not contain identifiers, URLs or secrets')


def make_annotation(kind, key, rater_id, label, rationale, labeled_at, guide=GUIDE_VERSION):
    a = dict(annotationId=str(uuid.uuid4()), targetType=kind, raterId=rater_id, label=label,
             phase='INDEPENDENT', sourceAnnotationIds=None, labelGuideVersion=guide,
             labeledAt=labeled_at, rationale=rationale, adjudicationNote=None)
    a.update(_target_fields(kind, key))
    validate_annotation(a)
    return a


def _target_fields(kind, key):
    if kind == 'PAGE_VISIT':
        return dict(visitId=key, windowId=None, stateVersion=None, referenceStateVersion=None)
    if kind == 'WINDOW':
        # P6 pending: RAW_ONLY review windows have no stateVersion; final exported dwell is the basis.
        return dict(visitId=None, windowId=key, stateVersion=None, referenceStateVersion=None)
    raise ValueError('Unsupported target type')


def target_key(a):
    return (a['targetType'], a['visitId'] if a['targetType'] == 'PAGE_VISIT' else a['windowId'],
            a['labelGuideVersion'])


def validate_annotation(a):
    if not isinstance(a, dict) or set(a) != ANNOTATION_FIELDS:
        raise ValueError('Annotation fields must match human_labels contract exactly')
    uuid.UUID(a['annotationId'])
    kind = a['targetType']
    if kind not in LABELS or a['label'] not in LABELS[kind]:
        raise ValueError('Label not allowed for target type')
    if a['stateVersion'] is not None or a['referenceStateVersion'] is not None:
        raise ValueError('RAW review labels have no state version (P6 pending)')
    if kind == 'PAGE_VISIT' and not (isinstance(a['visitId'], str) and a['visitId'] and a['windowId'] is None):
        raise ValueError('PAGE_VISIT requires visitId only')
    if kind == 'WINDOW' and not (isinstance(a['windowId'], str) and a['visitId'] is None):
        raise ValueError('WINDOW requires windowId only')
    if kind == 'WINDOW':
        uuid.UUID(a['windowId'])
    if not isinstance(a['labelGuideVersion'], str) or not a['labelGuideVersion']:
        raise ValueError('labelGuideVersion required')
    _timestamp(a['labeledAt'])
    if a['phase'] == 'INDEPENDENT':
        if not (isinstance(a['raterId'], str) and RATER.match(a['raterId'])):
            raise ValueError('INDEPENDENT label requires raterId')
        if a['sourceAnnotationIds'] is not None or a['adjudicationNote'] is not None:
            raise ValueError('INDEPENDENT label cannot reference other votes')
        validate_rationale(a['rationale'])
    elif a['phase'] == 'CONSENSUS':
        ids = a['sourceAnnotationIds']
        if a['raterId'] is not None or not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise ValueError('CONSENSUS requires raterId=null and source votes')
        for i in ids:
            uuid.UUID(i)
        validate_rationale(a['rationale'], required=False)
        validate_rationale(a['adjudicationNote'], required=False)
    else:
        raise ValueError('phase must be INDEPENDENT or CONSENSUS')
    return a


def check_labels(annotations):
    """Uniqueness rules from data-analysis-contract: one vote per (target, guide, rater),
    one consensus per (target, guide), consensus must cite existing independent votes."""
    seen, consensus, by_id = set(), set(), {}
    for a in annotations:
        validate_annotation(a)
        if a['annotationId'] in by_id:
            raise ValueError('Duplicate annotationId')
        by_id[a['annotationId']] = a
        key = target_key(a)
        if a['phase'] == 'INDEPENDENT':
            if (key, a['raterId']) in seen:
                raise ValueError('Duplicate independent vote')
            seen.add((key, a['raterId']))
        else:
            if key in consensus:
                raise ValueError('Duplicate consensus')
            consensus.add(key)
    for a in annotations:
        if a['phase'] == 'CONSENSUS':
            for i in a['sourceAnnotationIds']:
                src = by_id.get(i)
                if not src or src['phase'] != 'INDEPENDENT' or target_key(src) != target_key(a):
                    raise ValueError('Consensus must cite independent votes of the same target')
    return annotations


def votes_by_target(annotations):
    grouped = defaultdict(list)
    for a in annotations:
        if a['phase'] == 'INDEPENDENT':
            grouped[target_key(a)].append(a)
    return grouped


def plan_consensus(annotations, raters=3):
    """Split targets into majority (>=2 agree), review (all differ) and incomplete (<3 votes)."""
    majority, review, incomplete = {}, [], []
    for key, votes in sorted(votes_by_target(annotations).items()):
        if len(votes) != raters:
            incomplete.append(key)
            continue
        label, count = Counter(v['label'] for v in votes).most_common(1)[0]
        if count >= 2:
            majority[key] = (label, votes)
        else:
            review.append(key)
    return majority, review, incomplete


def build_consensus(annotations, decisions, labeled_at, raters=3):
    """Majority targets get an automatic CONSENSUS; disagreements only from explicit decisions."""
    check_labels(annotations)
    majority, review, incomplete = plan_consensus(annotations, raters)
    groups = votes_by_target(annotations)
    decided = {}
    for d in decisions:
        if set(d) != {'targetType', 'visitId', 'windowId', 'label', 'adjudicationNote'}:
            raise ValueError('Decision needs targetType, visitId, windowId, label, adjudicationNote')
        key = (d['targetType'], d['visitId'] if d['targetType'] == 'PAGE_VISIT' else d['windowId'], GUIDE_VERSION)
        if key not in groups or key in decided:
            raise ValueError('Decision target unknown or duplicated')
        if d['label'] not in LABELS[d['targetType']]:
            raise ValueError('Decision label not allowed')
        validate_rationale(d['adjudicationNote'])
        decided[key] = d
    out = []
    for key in sorted(set(majority) | set(decided)):
        votes = groups[key]
        if key in decided:
            label, note = decided[key]['label'], decided[key]['adjudicationNote']
        else:
            label, note = majority[key][0], None
        a = dict(annotationId=str(uuid.uuid4()), targetType=key[0], raterId=None, label=label,
                 phase='CONSENSUS', sourceAnnotationIds=sorted(v['annotationId'] for v in votes),
                 labelGuideVersion=key[2], labeledAt=labeled_at, rationale=None, adjudicationNote=note)
        a.update(_target_fields(key[0], key[1]))
        out.append(validate_annotation(a))
    unresolved = [k for k in review if k not in decided]
    return check_labels(list(annotations) + out), unresolved, incomplete


def fleiss_kappa(rows, categories):
    """rows: list of label lists, each with the same number (>=2) of raters. None if undefined."""
    if not rows:
        return None
    n = len(rows[0])
    if n < 2 or any(len(r) != n for r in rows):
        raise ValueError('Every item needs the same number of raters (>=2)')
    counts = [[r.count(c) for c in categories] for r in rows]
    total = len(rows) * n
    p_j = [sum(c[j] for c in counts) / total for j in range(len(categories))]
    p_bar = sum((sum(x * x for x in c) - n) / (n * (n - 1)) for c in counts) / len(rows)
    p_e = sum(p * p for p in p_j)
    if p_e == 1:
        return None
    return (p_bar - p_e) / (1 - p_e)


def kappa_report(annotations, raters=3):
    """Pre-adjudication votes only: 4-category kappa, plus 3-category kappa on items where
    every rater could judge (no UNJUDGEABLE)."""
    result = {}
    groups = votes_by_target(annotations)
    for kind, labels in LABELS.items():
        rows = [[v['label'] for v in votes] for key, votes in sorted(groups.items())
                if key[0] == kind and len(votes) == raters]
        judged = [r for r in rows if 'UNJUDGEABLE' not in r]
        result[kind] = dict(items=len(rows), kappa4=fleiss_kappa(rows, labels),
                            judgedItems=len(judged), kappa3=fleiss_kappa(judged, labels[:3]),
                            percentAgreement=(sum(len(set(r)) == 1 for r in rows) / len(rows)) if rows else None,
                            unjudgeableVotes=sum(r.count('UNJUDGEABLE') for r in rows),
                            distribution=dict(Counter(l for r in rows for l in r)))
    return result


def derived_rule_state(page_labels, durations_ms):
    """BE suffix rule (data-collection-spec §7) applied to HUMAN page labels.
    Comparison material only; never a substitute for an independent window label."""
    if len(page_labels) != 3 or len(durations_ms) != 3:
        raise ValueError('Three pages required')
    if any(l not in PAGE_LABELS for l in page_labels):
        raise ValueError('Unknown page label')
    if 'UNJUDGEABLE' in page_labels:
        return None
    suffix = []
    for label, duration in zip(reversed(page_labels), reversed(durations_ms)):
        if label in RELATED:
            break
        suffix.append(duration)
    if not suffix:
        return 'NORMAL'
    if len(suffix) == 3 or any(d >= LONG_DWELL_MS for d in suffix):
        return 'DRIFT'
    return 'TRANSITION' if len(suffix) == 2 else 'NORMAL'


def derived_states(records, consensus):
    """windowId -> derivedRuleState from CONSENSUS page labels (None when any page is missing)."""
    pages = {a['visitId']: a['label'] for a in consensus
             if a['phase'] == 'CONSENSUS' and a['targetType'] == 'PAGE_VISIT'}
    out = {}
    for r in records:
        visits = {v['visitId']: v for v in r['visits']}
        for w in r['windows']:
            labels = [pages.get(i) for i in w['visitIds']]
            out[window_id(w['visitIds'])] = (None if None in labels else derived_rule_state(
                labels, [visits[i]['activeDurationMs'] for i in w['visitIds']]))
    return out
