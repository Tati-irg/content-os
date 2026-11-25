"""Exercise both CLI entry points with an inherited OS network block."""
import ctypes as c
import errno
from hashlib import sha256
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

lib = c.CDLL('libseccomp.so.2')
lib.seccomp_init.argtypes = [c.c_uint32]
lib.seccomp_init.restype = c.c_void_p
lib.seccomp_syscall_resolve_name.argtypes = [c.c_char_p]
lib.seccomp_rule_add.argtypes = [c.c_void_p, c.c_uint32, c.c_int, c.c_uint]
lib.seccomp_load.argtypes = [c.c_void_p]
ctx = lib.seccomp_init(0x7fff0000)
assert ctx
for name in (b'socket', b'socketpair', b'connect', b'sendto', b'sendmsg', b'sendmmsg', b'io_uring_setup'):
    assert lib.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM,
                                lib.seccomp_syscall_resolve_name(name), 0) == 0
assert lib.seccomp_load(ctx) == 0
try:
    socket.socket()
except PermissionError:
    pass
else:
    raise AssertionError('Sockets enabled')

root = Path(__file__).resolve().parents[1]
publisher = root / 'publisher'


def sample_package(directory):
    material = directory / 'sample'
    source = directory / 'input.md'

    def coordinate(*args):
        subprocess.run([sys.executable, str(root/'coordinator/state.py'), str(material), *args],
                       check=True, capture_output=True, text=True)

    source.write_text('Synthetic input')
    coordinate('init', 'TEST-CYCLE', 'TEST-ASSET', 'TEST-GATE1', str(source))
    source.write_text('Synthetic evidence of GATE 1')
    coordinate('record-gate1', str(source), '--approved-by', 'Test approver', '--note', 'Fixture')
    source.write_text('Synthetic draft v1')
    coordinate('revise', str(source), '--note', 'Initial draft')
    source.write_text('Synthetic draft v2')
    coordinate('revise', str(source), '--note', 'Second draft')
    version = material / 'v2'
    for name in ('factcheck', 'visual', 'audit'):
        source.write_text(f'Synthetic {name}')
        coordinate('record', 'v2', name, str(source), '--note', 'Fixture')
    (version/'render').mkdir()
    from PIL import Image
    for number in (1, 2):
        Image.new('RGB', (32, 40), 'white').save(version/f'render/slide_{number:02d}.png')
    members = ['text.md', 'factcheck.md', 'visual.md', 'audit.md',
               'render/slide_01.png', 'render/slide_02.png']
    source.write_text(''.join(f'- [{name}]({name}) · `{sha256((version/name).read_bytes()).hexdigest()}`\n'
                              for name in members))
    coordinate('record', 'v2', 'package', str(source), '--note', 'Fixture')
    source.write_text('Synthetic evidence of GATE 2')
    coordinate('record', 'v2', 'gate2', str(source), '--note', 'Fixture')
    return material


with tempfile.TemporaryDirectory() as directory:
    cases = Path(directory)
    original = sample_package(cases)
    for scenario in ('ready', 'changed-text', 'changed-png', 'old-version', 'no-gate1', 'no-gate2', 'no-release'):
        pilot = cases / scenario
        shutil.copytree(original, pilot)
        manifest = pilot/'manifest.json'
        state = json.loads(manifest.read_text())
        if scenario in ('changed-text', 'changed-png'):
            name = 'text.md' if scenario == 'changed-text' else 'render/slide_01.png'
            with (pilot/'v2'/name).open('ab') as stream:
                stream.write(b'changed')
        elif scenario == 'no-gate1':
            (pilot/state['gate1_evidence']['file']).unlink()
        elif scenario == 'no-gate2':
            (pilot/state['versions']['v2']['results']['gate2']['file']).unlink()
        slot = pilot/'unused-slot.json'
        for script in ('publish.py', 'publish_carousel.py'):
            cmd = [sys.executable, str(publisher/script), '--manifest', str(manifest),
                   '--version', 'v1' if scenario == 'old-version' else 'v2']
            if scenario == 'ready':
                cmd.append('--check-ready')
            else:
                cmd.append('--publish')
                cmd.extend([str(slot)] if script == 'publish.py' else
                           [str(pilot/'v2/render'), '--id', state['asset_id'],
                            '--caption', str(pilot/'v2/text.md')])
            result = subprocess.run(cmd, capture_output=True, text=True)
            expectations = {'changed-text': 'SHA-256 mismatch: v2/text.md',
                            'changed-png': 'SHA-256 mismatch: render/slide_01.png',
                            'old-version': 'not active',
                            'no-gate1': 'approvals/gate1.json',
                            'no-gate2': 'v2/gate2.md',
                            'no-release': 'separate --release authorization is required'}
            if scenario == 'ready':
                assert result.returncode == 0 and json.loads(result.stdout)['package_ready'], result
            else:
                assert result.returncode != 0 and expectations[scenario] in result.stderr, result
                assert not (publisher.parent/'media'/state['asset_id']).exists()
            print(f'{script}: {scenario}: OK')
