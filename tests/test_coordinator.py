"""Offline smoke test using synthetic text, results and approvals."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
with TemporaryDirectory() as folder:
    root = Path(folder)
    source = root / 'sample.md'
    material = root / 'material'

    def call(*args, expect=0):
        result = subprocess.run([sys.executable, str(ROOT/'coordinator/state.py'), str(material), *args],
                                capture_output=True, text=True)
        assert result.returncode == expect, result.stderr
        return result.stdout or result.stderr

    source.write_text('Synthetic input')
    call('init', 'TEST-CYCLE', 'TEST-ASSET', 'TEST-GATE1', str(source))
    source.write_text('Synthetic draft v1')
    call('revise', str(source), '--note', 'Initial draft')
    for stage in ('factcheck', 'visual', 'audit', 'package', 'gate2'):
        source.write_text(f'Synthetic {stage} evidence for v1')
        call('record', 'v1', stage, str(source), '--note', 'Synthetic fixture')
    before = json.loads(call('verify'))
    assert before['gate2_current']
    source.write_text('Synthetic draft v2, edited')
    call('revise', str(source), '--note', 'Simulated author change')
    after = json.loads(call('verify'))
    assert after['current_version'] == 'v2' and not after['gate2_current']
    state = json.loads((material/'manifest.json').read_text())
    old = state['versions']['v1']['results']
    assert state['versions']['v1']['status'] == 'stale'
    assert all(record['status'] == 'stale' for record in old.values())
    assert old['gate2']['package_sha256'] == old['package']['sha256']
    assert state['versions']['v2']['results'] == {}
    assert 'current version' in call('record', 'v1', 'gate2', str(source),
                                    '--note', 'Old approval', expect=1)
    assert 'Record stages in order' in call('record', 'v2', 'gate2', str(source),
                                           '--note', 'Premature approval', expect=1)
    (material/'v2/text.md').write_text('Untracked edit')
    assert 'Checksum mismatch' in call('verify', expect=1)
    print('v1: synthetic approval current')
    print('v2: stale factcheck, visual, audit, package and GATE 2')
    print('Old and premature approvals rejected. Direct text edit detected by SHA-256.')
