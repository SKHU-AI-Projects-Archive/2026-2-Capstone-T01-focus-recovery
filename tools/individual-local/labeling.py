#!/usr/bin/env python3
"""Blind human labelling for v2 training-review data (#126). Guide: docs/data-collection/labeling-guide.md

serve      decrypt a verified training-review artifact in memory and run a loopback-only
           labelling page for ONE rater; only IDs, labels and rationales are written to disk.
report     Fleiss' kappa, distributions, majority candidates and the joint-review list.
consensus  write human_labels.jsonl (INDEPENDENT + CONSENSUS) from three raters' files.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset as d  # noqa: E402  (also puts ai/ on sys.path)
from training import labeling as L  # noqa: E402

UI = Path(__file__).resolve().parent / 'labeling_ui'
BODY_LIMIT = 16 * 1024


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def load_review(path, sha256, identity=None, synthetic=False):
    d.require(d.digest(Path(path).read_bytes()) == sha256, 'Trusted review SHA-256 required')
    manifest, _ = d.verify_artifact(path, identity, synthetic)
    d.require(manifest['schemaVersion'] == 'focus-training-review/1', 'training-review artifact required')
    payloads = d.read_payloads(path, identity, synthetic)
    return [d.parse(line) for line in payloads['review.jsonl'].splitlines()]


def read_labels(path):
    path = Path(path)
    if not path.exists():
        return []
    return [d.parse(line) for line in path.read_bytes().splitlines() if line.strip()]


def write_labels(path, annotations):
    """Atomic private replace; the file holds IDs, labels and rationales only."""
    path = Path(path)
    tmp = path.with_name(path.name + '.partial-' + uuid.uuid4().hex)
    d.private_write(tmp, b''.join(d.encoded(a) for a in annotations))
    os.replace(tmp, path)


class Session:
    def __init__(self, records, rater, labels_path, page_context, pilot):
        self.lock = threading.Lock()
        self.rater, self.labels_path = rater, Path(labels_path)
        window_ids = L.select_pilot(records) if pilot else None
        self.tasks, self.targets = L.build_tasks(records, rater, page_context, window_ids,
                                                 salt=secrets.token_bytes(16))
        self.by_target = {v: k for k, v in self.targets.items()}
        self.labels = {}
        for a in L.check_labels(read_labels(self.labels_path)):
            d.require(a['phase'] == 'INDEPENDENT' and a['raterId'] == rater, 'Labels file belongs to another rater')
            key = (a['targetType'], a['visitId'] if a['targetType'] == 'PAGE_VISIT' else a['windowId'])
            if key in self.by_target:  # labels outside this task set (e.g. pilot) are kept untouched
                self.labels[self.by_target[key]] = a
            else:
                self.labels[('extra', a['annotationId'])] = a

    def state(self):
        out = []
        for t in self.tasks:
            a = self.labels.get(t['taskId'])
            out.append(dict(t, saved=dict(label=a['label'], rationale=a['rationale']) if a else None))
        return dict(rater=self.rater, guide=L.GUIDE_VERSION, tasks=out)

    def save(self, task_id, label, rationale):
        with self.lock:
            d.require(task_id in self.targets, 'Unknown task')
            kind, key = self.targets[task_id]
            old = self.labels.get(task_id)
            a = L.make_annotation(kind, key, self.rater, label, rationale, now())
            if old:
                a['annotationId'] = old['annotationId']  # one vote per target: re-labelling replaces it
            self.labels[task_id] = a
            write_labels(self.labels_path, L.check_labels(list(self.labels.values())))
            return dict(label=a['label'], rationale=a['rationale'])


def make_handler(session, token, port):
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    static = {'/': ('index.html', 'text/html; charset=utf-8'),
              '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
              '/app.css': ('app.css', 'text/css; charset=utf-8')}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # no request logging: paths/bodies stay off the console
            pass

        def send(self, status, body, ctype='application/json; charset=utf-8'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def guard(self, api):
            if self.headers.get('Host') not in allowed_hosts:  # blocks DNS rebinding
                self.send(403, {'error': 'host'})
                return False
            if api and not secrets.compare_digest(self.headers.get('X-Label-Token', ''), token):
                self.send(403, {'error': 'token'})
                return False
            return True

        def do_GET(self):
            if self.path in static:
                if not self.guard(False):
                    return
                name, ctype = static[self.path]
                return self.send(200, (UI / name).read_bytes(), ctype)
            if self.path == '/api/state':
                if self.guard(True):
                    self.send(200, session.state())
                return
            self.send(404, {'error': 'not found'})

        def do_POST(self):
            if self.path != '/api/label' or not self.guard(True):
                if self.path != '/api/label':
                    self.send(404, {'error': 'not found'})
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'json required'})
            size = int(self.headers.get('Content-Length') or 0)
            if not 0 < size <= BODY_LIMIT:
                return self.send(413, {'error': 'size'})
            try:
                body = d.parse(self.rfile.read(size))
                d.require(isinstance(body, dict) and set(body) == {'taskId', 'label', 'rationale'}, 'Invalid body')
                self.send(200, session.save(body['taskId'], body['label'], body['rationale']))
            except (ValueError, TypeError) as exc:
                self.send(400, {'error': str(exc)})

    return Handler


def serve(a):
    records = load_review(a.review, a.sha256, a.identity, a.synthetic_plaintext)
    labels_dir = Path(a.labels_dir)
    d.require(labels_dir.is_dir(), 'labels-dir must be an existing private directory')
    session = Session(records, a.rater, labels_dir / f'labels-{a.rater}.jsonl', a.page_context, a.pilot)
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(('127.0.0.1', a.port), None)
    port = server.server_address[1]
    server.RequestHandlerClass = make_handler(session, token, port)
    pages = sum(t['targetType'] == 'PAGE_VISIT' for t in session.tasks)
    print(json.dumps(dict(rater=a.rater, pageTasks=pages, windowTasks=len(session.tasks) - pages,
                          labelsFile=str(session.labels_path), pilot=a.pilot, pageContext=a.page_context)))
    print(f'Open: http://127.0.0.1:{port}/#{token}  (do not share; Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def collect(files):
    annotations = []
    raters = set()
    for f in files:
        rows = read_labels(f)
        file_raters = {r['raterId'] for r in rows}
        d.require(len(file_raters) <= 1 and all(r['phase'] == 'INDEPENDENT' for r in rows), f'{f}: one rater, independent votes only')
        d.require(not (file_raters & raters), 'Each rater file must be distinct')
        raters |= file_raters
        annotations += rows
    return L.check_labels(annotations), raters


def report(a):
    annotations, raters = collect(a.labels)
    majority, review, incomplete = L.plan_consensus(annotations, a.raters)
    fmt = lambda key: dict(targetType=key[0], targetId=key[1], labelGuideVersion=key[2])
    result = dict(raters=sorted(raters), kappa=L.kappa_report(annotations, a.raters),
                  majorityTargets=len(majority), jointReview=[fmt(k) for k in review],
                  incomplete=[fmt(k) for k in incomplete])
    d.publish(Path(a.output), d.encoded(result))
    print(json.dumps(dict(raters=result['raters'], majorityTargets=len(majority),
                          jointReview=len(review), incomplete=len(incomplete))))


def consensus(a):
    annotations, raters = collect(a.labels)
    d.require(len(raters) == a.raters, f'{a.raters} distinct raters required')
    decisions = read_labels(a.decisions) if a.decisions else []
    out, unresolved, incomplete = L.build_consensus(annotations, decisions, now(), a.raters)
    d.publish(Path(a.output), b''.join(d.encoded(x) for x in out))
    print(json.dumps(dict(annotations=len(out), consensus=sum(x['phase'] == 'CONSENSUS' for x in out),
                          unresolved=len(unresolved), incomplete=len(incomplete))))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('serve')
    s.add_argument('review'); s.add_argument('--sha256', required=True); s.add_argument('--identity')
    s.add_argument('--rater', required=True); s.add_argument('--labels-dir', required=True)
    s.add_argument('--page-context', choices=L.PAGE_CONTEXTS, default='prior')
    s.add_argument('--pilot', action='store_true', help='20-window pilot from non-test goals')
    s.add_argument('--port', type=int, default=0)
    s.add_argument('--synthetic-plaintext', action='store_true', help=argparse.SUPPRESS)
    for name in ('report', 'consensus'):
        q = sub.add_parser(name)
        q.add_argument('labels', nargs='+'); q.add_argument('--output', required=True)
        q.add_argument('--raters', type=int, default=3)
        if name == 'consensus':
            q.add_argument('--decisions')
    a = p.parse_args(argv)
    if a.command == 'serve':
        d.require(a.identity or a.synthetic_plaintext, '--identity required for encrypted review data')
    {'serve': serve, 'report': report, 'consensus': consensus}[a.command](a)


if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        sys.exit('ERROR: ' + str(exc))
