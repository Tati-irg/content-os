"""Authorization for Meta endpoints, including Cloud HTTP secret substitution."""
import os
from urllib.parse import urlsplit


def meta_headers(url, scheme='Bearer'):
    target = urlsplit(url)
    if (target.scheme != 'https'
            or target.netloc not in {'graph.facebook.com', 'rupload.facebook.com'}):
        raise ValueError('Invalid Meta API destination')
    token = os.environ.get('META_PAGE_TOKEN')
    if not token:
        raise ValueError('META_PAGE_TOKEN is not set')
    # Pass the environment binding as-is. Cloud replaces its placeholder in transit.
    return {'Authorization': f'{scheme} {token}'}
