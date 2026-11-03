"""Fetch new TMKOC uploads, refresh stats, rebuild the site.

  python pipeline/update.py quick   # new uploads only (a few quota units)
  python pipeline/update.py full    # quick + refresh views/likes of every video (~250 units)

Needs the YT_KEY environment variable (YouTube Data API v3 key). Standard library only.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEOS = os.path.join(ROOT, 'data', 'videos.json')
UPLOADS = 'UU54_ux4BnaJwkVFn5M391XQ'      # uploads playlist of the official channel
CHANNEL = 'UC54_ux4BnaJwkVFn5M391XQ'
KEY = os.environ.get('YT_KEY', '')


class Quota(Exception):
    pass


def api(endpoint, **params):
    params['key'] = KEY
    url = 'https://www.googleapis.com/youtube/v3/' + endpoint + '?' + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as ex:
            body = ex.read().decode('utf-8', 'replace')
            if ex.code == 403 and 'quota' in body.lower():
                raise Quota()
            if ex.code in (400, 401, 403):
                raise SystemExit('YouTube API error %s: %s' % (ex.code, body[:300]))
            if ex.code == 404:
                return {'items': []}
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    raise SystemExit('YouTube API unreachable')


def raw_videos(ids):
    out = []
    for i in range(0, len(ids), 50):
        for v in api('videos', part='snippet,contentDetails,statistics,status', id=','.join(ids[i:i + 50])).get('items', []):
            if v['snippet'].get('channelId') != CHANNEL:
                continue
            out.append({'id': v['id'], 'title': v['snippet']['title'], 'description': v['snippet'].get('description', '')[:600],
                        'published': v['snippet']['publishedAt'], 'duration': v['contentDetails']['duration'],
                        'views': int(v['statistics'].get('viewCount', 0)), 'likes': int(v['statistics'].get('likeCount', 0)),
                        'tags': v['snippet'].get('tags', [])[:12], 'embeddable': v['status'].get('embeddable', True)})
    return out


def scan_new(known, cutoff):
    """Walk the uploads playlist newest-first until everything on a page is older than cutoff."""
    ids, token = [], None
    while True:
        p = dict(part='contentDetails', playlistId=UPLOADS, maxResults=50)
        if token:
            p['pageToken'] = token
        d = api('playlistItems', **p)
        items = d.get('items', [])
        for it in items:
            vid, pub = it['contentDetails']['videoId'], it['contentDetails'].get('videoPublishedAt', '9999')[:10]
            if pub >= cutoff and vid not in known:
                ids.append(vid)
        token = d.get('nextPageToken')
        oldest = min((it['contentDetails'].get('videoPublishedAt', '9999')[:10] for it in items), default='0000')
        if not token or oldest < cutoff:
            return ids


def main(mode):
    if not KEY:
        raise SystemExit('Set YT_KEY')
    videos = json.load(open(VIDEOS, encoding='utf-8'))
    known = {v['id'] for v in videos}
    changed, notes = False, []
    try:
        cutoff = (date.fromisoformat(max(v['p'] for v in videos)) - timedelta(days=3)).isoformat()
        new_ids = scan_new(known, cutoff)
        added = [r for r in (lib.ingest(x) for x in raw_videos(new_ids)) if r]
        if added:
            videos += added
            changed = True
            notes.append('%d new' % len(added))
        if mode == 'full':
            fresh = {x['id']: x for x in raw_videos([v['id'] for v in videos])}
            kept = []
            for v in videos:
                f = fresh.get(v['id'])
                if f is None or not f['embeddable']:
                    notes.append('dropped ' + v['id'])
                    continue
                v['v'], v['l'] = f['views'], f['likes']
                kept.append(v)
            videos, changed = kept, True
    except Quota:
        notes.append('quota exhausted, will retry next run')
    if changed:
        videos.sort(key=lambda o: (o['p'], o['id']))
        json.dump(videos, open(VIDEOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    out = os.path.join(ROOT, 'public')
    os.makedirs(out, exist_ok=True)
    if changed or not os.path.exists(os.path.join(out, 'index.html')):
        lib.render(lib.build(videos), os.path.join(ROOT, 'web', 'template.html'), os.path.join(out, 'index.html'))
    print(mode, '|', ', '.join(notes) or 'nothing new', '|', len(videos), 'videos')
    gh = os.environ.get('GITHUB_OUTPUT')
    if gh:
        open(gh, 'a').write('changed=%s\n' % ('true' if changed else 'false'))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'quick')
