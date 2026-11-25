#!/usr/bin/env python3
"""Publish a rendered carousel to Instagram (@irg_psy) via the Graph API.

Without --publish slide and caption validation is local.
Publishing requires active GATE 1 and GATE 2 evidence, a verified package,
and separate --release authorization.

Usage: publish_carousel.py SLIDES_DIR --id ASSET_ID --caption CAPTION.txt
Readiness: publish_carousel.py --check-ready --manifest MANIFEST.json --version VERSION
"""
import argparse, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image

from media_hosting import MEDIA_PUSH_REF, media_url, require_media_origin
from meta_auth import meta_headers
import release_guard

GRAPH = 'https://graph.facebook.com/v21.0'
IG_USER = '17841402153358869'  # @irg_psy
REPO = Path(__file__).resolve().parent.parent


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(method, path, **params):
    data = urllib.parse.urlencode(params).encode() if method == 'POST' else None
    url = f'{GRAPH}/{path}' + ('' if method == 'POST' else '?' + urllib.parse.urlencode(params))
    try:
        request = urllib.request.Request(url, data=data, method=method, headers=meta_headers(url))
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=120) as response:
            body = json.load(response)
    except ValueError as e:
        if isinstance(e, json.JSONDecodeError):
            sys.exit('Meta Graph API returned an invalid response')
        sys.exit(str(e))
    except urllib.error.HTTPError as e:
        sys.exit(f'Meta Graph API: HTTP {e.code}')
    if 'error' in body:
        sys.exit('Meta Graph API returned an error')
    return body


def wait_ready(cid, tries=30):
    for _ in range(tries):
        st = api('GET', cid, fields='status_code,status')
        if st.get('status_code') == 'FINISHED':
            return
        if st.get('status_code') in ('ERROR', 'EXPIRED'):
            sys.exit(f'container {cid}: {st}')
        time.sleep(3)
    sys.exit(f'container {cid} not ready in time')


def host_images(slides_dir, asset_id):
    pngs = sorted(Path(slides_dir).glob('slide_*.png'))
    if not 2 <= len(pngs) <= 10:
        sys.exit(f'Instagram carousel needs 2–10 slides, found {len(pngs)}')
    try:
        require_media_origin(REPO)
    except ValueError as e:
        sys.exit(str(e))
    dest = REPO / 'media' / asset_id
    dest.mkdir(parents=True, exist_ok=True)
    for p in pngs:  # Instagram accepts JPEG only
        Image.open(p).convert('RGB').save(dest / (p.stem + '.jpg'), quality=92, optimize=True)
    git = ['git', '-C', str(REPO), '-c', 'user.name=redkova13-ai', '-c', 'user.email=redkova13-ai@users.noreply.github.com']
    subprocess.run(git + ['add', str(dest)], check=True)
    if subprocess.run(git + ['diff', '--cached', '--quiet']).returncode:
        subprocess.run(git + ['commit', '-qm', f'media: {asset_id}'], check=True)
        subprocess.run(git + ['push', '-q', 'origin', MEDIA_PUSH_REF], check=True)
    urls = [media_url(asset_id, p.stem + '.jpg') for p in pngs]
    for u in urls:  # raw CDN can lag a few seconds after push
        for _ in range(20):
            try:
                urllib.request.urlopen(urllib.request.Request(u, method='HEAD'), timeout=20)
                break
            except Exception:
                time.sleep(3)
        else:
            sys.exit(f'image not reachable: {u}')
    return urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slides_dir', nargs='?')
    ap.add_argument('--id', help='CONTENT ASSET ID, used as the media folder name')
    ap.add_argument('--caption', help='text file with the post caption')
    ap.add_argument('--publish', action='store_true', help='publish with coordinator approvals and release authorization')
    release_guard.add_options(ap)
    a = ap.parse_args()
    if a.check_ready and a.publish:
        ap.error('--check-ready and --publish are mutually exclusive')
    try:
        with tempfile.TemporaryDirectory(prefix='content-os-release-') as directory:
            return run_cli(a, Path(directory))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        sys.exit(f'BLOCKED: {e}')


def run_cli(a, directory):
    if a.check_ready:
        release_guard.print_ready(release_guard.check_args(a, a.id))
        return
    release_guard.require(a.id and a.caption and a.slides_dir, 'slides_dir, --id and --caption are required')
    slides = Path(a.slides_dir).resolve()
    caption_file = Path(a.caption).resolve()
    if a.publish:
        bundle = release_guard.check_args(a, a.id)
        release_guard.require(a.release, 'separate --release authorization is required')
        caption_name = release_guard.approved_input(bundle, caption_file)
        pngs = sorted(slides.glob('slide_*.png'))
        release_guard.require(2 <= len(pngs) <= 10, 'Instagram carousel needs 2–10 slides')
        names = [release_guard.approved_input(bundle, p) for p in pngs]
        release_guard.snapshot(bundle, directory)
        slides = directory / Path(names[0]).parent
        release_guard.require(sorted(p.relative_to(directory).as_posix()
                                     for p in slides.glob('slide_*.png')) == names,
                              'slide list does not match the approved snapshot')
        caption_file = directory / caption_name
    caption = caption_file.read_text(encoding='utf-8').strip()
    release_guard.require(len(caption) <= 2200, 'Instagram caption exceeds 2200 characters')
    if not a.publish:
        count = len(list(slides.glob('slide_*.png')))
        release_guard.require(2 <= count <= 10, 'Instagram carousel needs 2–10 slides')
        print(json.dumps({'asset_id': a.id, 'slides': count, 'mode': 'dry_run', 'published': False}))
        return
    release_guard.still_current(a, bundle)
    release_guard.authorize(bundle, a.release, 'publish_carousel.py', ['ig'],
                                {'caption': caption_name, 'slides': names})
    urls = host_images(slides, a.id)
    children = []
    for u in urls:
        c = api('POST', f'{IG_USER}/media', image_url=u, is_carousel_item='true')['id']
        children.append(c)
    for c in children:
        wait_ready(c)
    carousel = api('POST', f'{IG_USER}/media', media_type='CAROUSEL', children=','.join(children), caption=caption)['id']
    wait_ready(carousel)
    result = {'asset_id': a.id, 'slides': len(urls), 'container': carousel, 'published': False}

    if a.publish:
        media = api('POST', f'{IG_USER}/media_publish', creation_id=carousel)['id']
        info = api('GET', media, fields='permalink,timestamp')
        result.update(published=True, media_id=media, permalink=info.get('permalink'), timestamp=info.get('timestamp'))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
