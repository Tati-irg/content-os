"""Local coordinator package verification before publisher side effects."""
import hashlib
import json
from pathlib import Path
import re
import shutil


MEMBER = re.compile(r'- \[([^\]]+)\]\(([^)]+)\) · `([0-9a-f]{64})`')
STAGES = ('factcheck', 'visual', 'audit', 'package', 'gate2')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(value, dict), 'expected a JSON object')
    return value


def checked_file(root, entry):
    name = Path(entry['file'])
    require(not name.is_absolute() and '..' not in name.parts, 'package path must be relative')
    path = root / name
    require(path.resolve() == path and path.is_file(), f'missing or unsafe file: {name}')
    require(checksum(path) == entry['sha256'], f'SHA-256 mismatch: {name}')
    return path


def readiness(manifest, version, asset_id=None):
    root = manifest.resolve().parent
    state = read_json(manifest)
    asset = state['asset_id']
    require(isinstance(asset, str) and re.fullmatch(r'[A-Za-z0-9_-]+', asset), 'invalid asset_id')
    require(asset_id is None or asset == asset_id, 'asset_id mismatch')
    require(version == state['current_version'], 'requested version is not active')
    active = state['versions'][version]
    require(active['status'] == 'current', 'version is not current')
    require(state['status'] == 'gate2_recorded', 'GATE 2 is missing or inactive')
    checked_file(root, state['input'])
    g1_file = checked_file(root, state['gate1_evidence'])
    gate1 = read_json(g1_file)
    require(gate1['decision'] == 'approved' and gate1['asset_id'] == asset
            and gate1['cycle_id'] == state['cycle_id'] and gate1['gate1_id'] == state['gate1']
            and gate1['input_sha256'] == state['input']['sha256']
            and gate1['approved_by'], 'GATE 1 is missing or does not cover this input')
    checked_file(root, gate1['source'])
    text = checked_file(root, active['text'])
    results = active['results']
    require(all(stage in results for stage in STAGES), 'required results or GATE 2 missing')
    paths = {}
    for stage in STAGES:
        entry = results[stage]
        require(entry['status'] == 'current' and entry['text_sha256'] == active['text']['sha256'],
                f'{stage} is stale')
        paths[stage] = checked_file(root, entry)
    package_hash = results['package']['sha256']
    require(results['gate2']['package_sha256'] == package_hash, 'GATE 2 package SHA-256 mismatch')
    package = paths['package']
    members = {}
    content = package.read_bytes()
    require(hashlib.sha256(content).hexdigest() == package_hash, 'package changed while reading')
    for line in content.decode('utf-8').splitlines():
        if not line.startswith('- ['):
            continue
        match = MEMBER.fullmatch(line)
        require(match is not None and match[1] == match[2], 'invalid package member entry')
        name, digest = match[2], match[3]
        path = checked_file(package.parent, {'file': name, 'sha256': digest})
        require(path not in members, 'duplicate package member')
        members[path] = digest
    require({text, paths['factcheck'], paths['visual'], paths['audit']} <= members.keys(),
            'package does not include the current text and checks')
    return {'asset_id': asset, 'version': version, 'package_sha256': package_hash,
            'root': package.parent, 'members': members}


def authorize(bundle, release_file, publisher, platforms, inputs):
    require(release_file is not None, 'separate --release authorization is required')
    release = read_json(release_file)
    expected = {key: bundle[key] for key in ('asset_id', 'version', 'package_sha256')}
    expected.update(action='publish', publisher=publisher, platforms=sorted(platforms), inputs=inputs)
    require(all(release.get(key) == value for key, value in expected.items())
            and release.get('authorized_by') and release.get('authorized_at'),
            'release authorization does not match the package, inputs or platforms')


def still_current(args, bundle):
    current = check_args(args, bundle['asset_id'])
    require(current == bundle, 'approved package changed while preparing the release')


def approved_input(bundle, path):
    path = path.resolve()
    require(path in bundle['members'], 'publisher input is not an approved package member')
    return path.relative_to(bundle['root']).as_posix()


def snapshot(bundle, directory):
    for path, digest in bundle['members'].items():
        copy = directory / path.relative_to(bundle['root'])
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copy)
        require(checksum(copy) == digest, 'approved file changed while preparing the release')


def add_options(parser):
    parser.add_argument('--manifest', type=Path, help='local coordinator manifest.json')
    parser.add_argument('--version', help='explicit active version, such as v2')
    parser.add_argument('--check-ready', action='store_true', help='check the approved package offline')
    parser.add_argument('--release', type=Path, help='separate release authorization JSON')


def check_args(args, asset_id=None):
    require(args.manifest is not None and args.version, '--manifest and --version are required')
    return readiness(args.manifest, args.version, asset_id)


def print_ready(bundle):
    print(json.dumps({k: bundle[k] for k in ('asset_id', 'version', 'package_sha256')}
                     | {'package_ready': True, 'release_checked': False}))
