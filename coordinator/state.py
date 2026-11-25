#!/usr/bin/env python3
"""Local state for a single coordinator. No network or publishing operations."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

RESULTS = ('factcheck', 'visual', 'audit', 'package', 'gate2')
FILES = dict(zip(RESULTS, ('factcheck.md', 'visual.md', 'audit.md', 'package.md', 'gate2.md')))


def digest(data):
    return sha256(data).hexdigest()


def save(path, state):
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        name = Path(temp.name)
        try:
            temp.write((json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
            temp.flush()
            os.fsync(temp.fileno())
            name.replace(path)
        finally:
            name.unlink(missing_ok=True)


def event(state, action, note, **details):
    state['changes'].append({'at': datetime.now(timezone.utc).isoformat(),
                             'action': action, 'note': note, **details})


def verify(root, entry):
    if digest((root / entry['file']).read_bytes()) != entry['sha256']:
        raise ValueError(f"Checksum mismatch: {entry['file']}")


def validate(root, state):
    verify(root, state['input'])
    if state['current_version'] is None:
        return None
    version = state['versions'][state['current_version']]
    verify(root, version['text'])
    for stage, entry in version['results'].items():
        verify(root, entry)
        if entry['text_sha256'] != version['text']['sha256']:
            raise ValueError(f'{stage} is bound to different text')
    gate = version['results'].get('gate2')
    if gate and gate['package_sha256'] != version['results']['package']['sha256']:
        raise ValueError('GATE 2 is bound to a different package')
    return version


def store(root, relative, data):
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as f:
        f.write(data)
    return {'file': relative, 'sha256': digest(data)}


def run(a):
    root = a.directory.resolve()
    if any((d / '.git').is_file() or (d / '.git' / 'HEAD').is_file() for d in (root, *root.parents)):
        raise ValueError('Use a private material directory outside Git')
    path = root / 'manifest.json'
    if a.command == 'init':
        card = a.card.read_bytes()
        root.mkdir(parents=True)
        state = {'cycle_id': a.cycle, 'asset_id': a.asset, 'gate1': a.gate1,
                 'current_version': None, 'status': 'on_hold', 'publication_date': None,
                 'exit_confirmed': False, 'input': store(root, 'input.md', card),
                 'versions': {}, 'changes': []}
        event(state, 'initialized', 'Input recorded. Development is on hold.')
    else:
        state = json.loads(path.read_text())
        version = validate(root, state)
        if a.command == 'verify':
            print(json.dumps({'asset_id': state['asset_id'],
                              'current_version': state['current_version'],
                              'status': state['status'],
                              'gate2_current': bool(version and 'gate2' in version['results'])},
                             ensure_ascii=False))
            return
        if a.command == 'record-gate1':
            if 'gate1_evidence' in state:
                raise ValueError('GATE 1 evidence is already recorded')
            evidence = {'asset_id': state['asset_id'], 'cycle_id': state['cycle_id'],
                        'gate1_id': state['gate1'], 'input_sha256': state['input']['sha256'],
                        'decision': 'approved', 'approved_by': a.approved_by}
            if not a.approved_by.strip():
                raise ValueError('An approver is required')
            source = a.file.read_bytes()
            if not source.strip():
                raise ValueError('GATE 1 source is empty')
            evidence['source'] = store(root, 'approvals/gate1-source.md', source)
            state['gate1_evidence'] = store(
                root, 'approvals/gate1.json', (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode())
            event(state, 'gate1_evidence_linked', a.note)
        elif a.command == 'revise':
            data = a.file.read_bytes()
            unchanged = version is not None and digest(data) == version['text']['sha256']
            if a.visual_only and not unchanged:
                raise ValueError('A visual-only revision requires identical text')
            if unchanged and not a.visual_only:
                raise ValueError('Text is unchanged')
            old = state['current_version']
            new = f"v{len(state['versions']) + 1}"
            entry = store(root, f'{new}/text.md', data)
            stale = []
            if version:
                version['status'] = 'stale'
                for stage, result in version['results'].items():
                    result['status'] = 'stale'
                    stale.append(stage)
            state['versions'][new] = {'status': 'current', 'text': entry, 'results': {}}
            state['current_version'] = new
            state['status'] = 'text_ready'
            event(state, 'visual_revision' if a.visual_only else 'text_revision',
                  a.note, version=new, supersedes=old, stale=stale)
        elif a.command == 'record':
            if not version or a.version != state['current_version']:
                raise ValueError('Result must refer to the current version')
            previous = RESULTS[:RESULTS.index(a.stage)]
            results = version['results']
            if set(results) != set(previous):
                raise ValueError('Record stages in order. For skipped fact-check record the reason.')
            entry = store(root, f'{a.version}/{FILES[a.stage]}', a.file.read_bytes())
            entry.update(status='current', text_sha256=version['text']['sha256'])
            if a.stage == 'gate2':
                entry['package_sha256'] = results['package']['sha256']
            results[a.stage] = entry
            state['status'] = {'package': 'awaiting_gate2', 'gate2': 'gate2_recorded'}.get(
                a.stage, f'{a.stage}_recorded')
            event(state, 'result_recorded', a.note, version=a.version, stage=a.stage)
    save(path, state)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('directory', type=Path)
    commands = cli.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    for name in ('cycle', 'asset', 'gate1'):
        init.add_argument(name)
    init.add_argument('card', type=Path)
    gate1 = commands.add_parser('record-gate1')
    gate1.add_argument('file', type=Path)
    gate1.add_argument('--approved-by', required=True)
    gate1.add_argument('--note', required=True)
    revise = commands.add_parser('revise')
    revise.add_argument('file', type=Path)
    revise.add_argument('--note', required=True)
    revise.add_argument('--visual-only', action='store_true')
    record = commands.add_parser('record')
    record.add_argument('version')
    record.add_argument('stage', choices=RESULTS)
    record.add_argument('file', type=Path)
    record.add_argument('--note', required=True)
    commands.add_parser('verify')
    try:
        run(cli.parse_args())
    except (OSError, ValueError) as exc:
        cli.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
