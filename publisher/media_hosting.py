"""Shared destination for media uploads and public GitHub Raw URLs."""
import subprocess
from urllib.parse import quote


MEDIA_REPOSITORY = 'Tati-irg/content-os'
MEDIA_BRANCH = 'main'
MEDIA_GIT_URL = f'https://github.com/{MEDIA_REPOSITORY}.git'
MEDIA_BASE_URL = f'https://raw.githubusercontent.com/{MEDIA_REPOSITORY}/{MEDIA_BRANCH}/media/'
MEDIA_PUSH_REF = f'HEAD:refs/heads/{MEDIA_BRANCH}'


def media_url(asset_id, filename):
    return MEDIA_BASE_URL + quote(asset_id, safe='') + '/' + quote(filename, safe='')


def require_media_origin(repo):
    """Check effective fetch and push URLs before creating or staging media."""
    expected = MEDIA_GIT_URL.casefold().removesuffix('.git')
    command = ['git', '-C', str(repo), 'remote', 'get-url', '--all']
    for options in ([], ['--push']):
        result = subprocess.run(command + options + ['origin'], capture_output=True, text=True)
        urls = [url.rstrip('/').casefold().removesuffix('.git') for url in result.stdout.splitlines()]
        if result.returncode or urls != [expected]:
            raise ValueError(f'Media hosting requires origin fetch and push URLs to match {MEDIA_GIT_URL}')
