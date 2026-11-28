"""#126 labelling tool: verified review input, loopback server guards, rater files, report/consensus."""
from collections import Counter
import http.client
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import threading
import types
import unittest
from http.server import ThreadingHTTPServer

import dataset as d
import labeling as tool
from training import labeling as L
from training.raw_review import review_records


def review_artifact(path, sessions=2):
    t = dict(goals=[dict(sourceInstanceId='src', goalId='G1', description='Public Python task')], sessions=[], visits=[])
    for s in range(sessions):
        sid = f's{s}'
        t['sessions'].append(dict(sourceInstanceId='src', sessionId=sid, participantId='participant-secret',
                                  goalId='G1', scenario='CLEAR_DRIFT', collectionStatus='COMPLETE'))
        t['visits'] += [dict(sourceInstanceId='src', sessionId=sid, visitId=f'{sid}-v{i}', sequence=i, title=f'Page {i}',
                             content='Python tutorial body text. ' * 4, searchQuery=None, extractionStatus='SUCCESS',
                             activeDurationMs=5000, tabSwitchCount=0, behaviorVersion=0, browserTabKey='tab',
                             normalizedUrl='https://docs.python.org/3/', domain='docs.python.org',
                             isSearchResultPage=False, visitedAt='2026-11-12T00:00:00.000Z') for i in range(1, 5)]
    records = review_records(t)
    raw = b''.join(d.encoded(r) for r in records)
    manifest = dict(schemaVersion='focus-training-review/1', sessions=len(records),
                    visits=sum(len(r['visits']) for r in records), windows=sum(len(r['windows']) for r in records),
                    rawSha256=d.digest(raw), labelStatus='UNLABELLED', privacyReview='REQUIRED',
                    splitCounts=dict(Counter(r['split'] for r in records)))
    files = {'review.jsonl': raw, 'manifest.json': d.encoded(manifest)}
    files['checksums.sha256'] = ''.join(d.digest(v) + '  ' + k + '\n' for k, v in sorted(files.items())).encode()
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name); info.size = len(data); tar.addfile(info, io.BytesIO(data))
    path.write_bytes(out.getvalue())
    return d.digest(out.getvalue())


class LabelingToolTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.review = self.root / 'review.tar'
        self.sha = review_artifact(self.review)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def session(self, rater='R1'):
        records = tool.load_review(self.review, self.sha, synthetic=True)
        return tool.Session(records, rater, self.root / f'labels-{rater}.jsonl', 'prior', False)

    def test_review_requires_trusted_sha_and_plaintext_only_for_synthetic(self):
        with self.assertRaises(ValueError):
            tool.load_review(self.review, '0' * 64, synthetic=True)
        with self.assertRaises(ValueError):
            tool.load_review(self.review, self.sha)

    def test_labels_file_has_ids_only_and_relabel_replaces_vote(self):
        s = self.session()
        page = next(t for t in s.tasks if t['targetType'] == 'PAGE_VISIT')
        s.save(page['taskId'], 'DIRECT', '목표 직접 수행')
        s.save(page['taskId'], 'UNRELATED', '다시 보니 무관')
        rows = tool.read_labels(s.labels_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['label'], 'UNRELATED')
        stored = s.labels_path.read_text(encoding='utf-8')
        for leaked in ('Python tutorial body', 'participant-secret', 'CLEAR_DRIFT', 'Public Python task'):
            self.assertNotIn(leaked, stored)
        again = self.session()  # reload keeps the vote; taskIds are salted per run, matched by target
        self.assertNotIn(page['taskId'], [t['taskId'] for t in again.tasks])
        saved = [t['saved'] for t in again.state()['tasks'] if t['saved']]
        self.assertEqual(saved, [dict(label='UNRELATED', rationale='다시 보니 무관')])
        with self.assertRaises(ValueError):
            s.save(page['taskId'], 'NORMAL', 'wrong label set')
        with self.assertRaises(ValueError):
            tool.Session(tool.load_review(self.review, self.sha, synthetic=True), 'R2', s.labels_path, 'prior', False)

    def test_server_requires_loopback_host_and_token(self):
        s = self.session()
        server = ThreadingHTTPServer(('127.0.0.1', 0), None)
        port = server.server_address[1]
        server.RequestHandlerClass = tool.make_handler(s, 'tok', port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def call(method, path, headers=None, body=None):
                c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                c.request(method, path, body=body, headers=headers or {})
                r = c.getresponse(); data = r.read(); c.close()
                return r.status, r.getheader('Content-Security-Policy'), data
            host = {'Host': f'127.0.0.1:{port}'}
            self.assertEqual(call('GET', '/', host)[0], 200)
            self.assertEqual(call('GET', '/', {'Host': f'evil.example:{port}'})[0], 403)
            self.assertEqual(call('GET', '/api/state', host)[0], 403)
            status, csp, data = call('GET', '/api/state', dict(host, **{'X-Label-Token': 'tok'}))
            self.assertEqual(status, 200)
            self.assertIn("default-src 'self'", csp)
            tasks = json.loads(data)['tasks']
            self.assertNotIn('participant-secret', data.decode())
            body = json.dumps(dict(taskId=tasks[0]['taskId'], label=L.LABELS[tasks[0]['targetType']][0], rationale='근거')).encode()
            hdr = dict(host, **{'X-Label-Token': 'tok', 'Content-Type': 'application/json'})
            self.assertEqual(call('POST', '/api/label', hdr, body)[0], 200)
            self.assertEqual(call('POST', '/api/label', dict(host, **{'Content-Type': 'application/json'}), body)[0], 403)
            self.assertEqual(call('POST', '/api/label', hdr, b'{"taskId":"x"}')[0], 400)
        finally:
            server.shutdown(); server.server_close()

    def test_report_and_consensus_from_three_raters(self):
        files = []
        for rater, label in (('R1', 'DIRECT'), ('R2', 'DIRECT'), ('R3', 'UNRELATED')):
            s = self.session(rater)
            for t in s.tasks:
                s.save(t['taskId'], label if t['targetType'] == 'PAGE_VISIT' else 'NORMAL', '근거')
            files.append(str(s.labels_path))
        tool.report(types.SimpleNamespace(labels=files, output=str(self.root / 'report.json'), raters=3))
        rep = json.loads((self.root / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(rep['raters'], ['R1', 'R2', 'R3'])
        self.assertEqual(rep['kappa']['PAGE_VISIT']['items'], 8)
        out = self.root / 'human_labels.jsonl'
        tool.consensus(types.SimpleNamespace(labels=files, output=str(out), raters=3, decisions=None))
        rows = tool.read_labels(out)
        L.check_labels(rows)
        cons = [r for r in rows if r['phase'] == 'CONSENSUS']
        self.assertEqual(len(cons), 8 + 4)
        self.assertTrue(all(r['label'] in ('DIRECT', 'NORMAL') for r in cons))
        with self.assertRaises(ValueError):  # same rater twice
            tool.collect([files[0], files[0]])


if __name__ == '__main__':
    unittest.main()
