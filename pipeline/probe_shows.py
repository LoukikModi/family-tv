"""One-off probe: what do the official CID and Hasya Jatra YouTube channels offer?

Writes data/probe.json with channel ids, upload counts and how many long full-episode
style videos match each show. Needs YT_KEY. Standard library only.
"""
import json, os, re, sys, urllib.error, urllib.parse, urllib.request

KEY = os.environ.get('YT_KEY', '')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'probe.json')
CID_PLAYLIST = 'PLzufeTFnhupxVg-1DHmZAsaWLZ_kKPNRh'   # "full episodes of CID" link from Sony's descriptions
MAX_PAGES = 120                                         # up to 6,000 newest uploads per channel


def api(endpoint, **params):
    params['key'] = KEY
    url = 'https://www.googleapis.com/youtube/v3/' + endpoint + '?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as ex:
        return {'error': ex.code, 'body': ex.read().decode('utf-8', 'replace')[:300], 'items': []}


def dur(s):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', s or '')
    h, mi, se = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mi * 60 + se


def scan(playlist, title_re, pages=MAX_PAGES):
    """Walk a playlist, keep titles matching title_re, then fetch durations for those."""
    hits, seen, token = [], 0, ''
    for _ in range(pages):
        d = api('playlistItems', part='snippet', playlistId=playlist, maxResults=50, pageToken=token)
        for it in d.get('items', []):
            seen += 1
            sn = it['snippet']
            if re.search(title_re, sn.get('title', ''), re.I):
                hits.append({'id': sn['resourceId']['videoId'], 't': sn['title'], 'p': sn['publishedAt'][:10]})
        token = d.get('nextPageToken', '')
        if not token:
            break
    for i in range(0, len(hits), 50):
        chunk = hits[i:i + 50]
        d = api('videos', part='contentDetails,statistics,status', id=','.join(h['id'] for h in chunk))
        info = {v['id']: v for v in d.get('items', [])}
        for h in chunk:
            v = info.get(h['id'])
            if v:
                h['s'] = dur(v['contentDetails'].get('duration'))
                h['v'] = int(v.get('statistics', {}).get('viewCount', 0))
                h['emb'] = v.get('status', {}).get('embeddable', False)
    return seen, hits


def summarize(hits):
    ok = [h for h in hits if h.get('emb') and h.get('s', 0) >= 1200]
    ok.sort(key=lambda h: h['p'])
    return {
        'matched': len(hits),
        'not_embeddable': sum(1 for h in hits if not h.get('emb')),
        'embeddable_but_short': sum(1 for h in hits if h.get('emb') and h.get('s', 0) < 1200),
        'not_embeddable_20min_plus': sum(1 for h in hits if not h.get('emb') and h.get('s', 0) >= 1200),
        'embeddable_20min_plus': len(ok),
        'oldest': ok[0]['p'] if ok else None,
        'newest': ok[-1]['p'] if ok else None,
        'by_year': {y: sum(1 for h in ok if h['p'].startswith(y)) for y in sorted({h['p'][:4] for h in ok})},
        'sample_newest': [{'t': h['t'][:90], 'p': h['p'], 's': h['s'], 'v': h['v']} for h in ok[-5:]],
        'sample_oldest': [{'t': h['t'][:90], 'p': h['p'], 's': h['s'], 'v': h['v']} for h in ok[:3]],
    }


def find_channel(handles, query):
    for hd in handles:
        d = api('channels', part='snippet,contentDetails,statistics', forHandle=hd)
        if d.get('items'):
            c = d['items'][0]
            return c
    d = api('search', part='snippet', q=query, type='channel', maxResults=3)
    return {'search_candidates': [(i['snippet']['channelId'], i['snippet']['title']) for i in d.get('items', [])]}


def chan_info(c):
    if 'id' not in c:
        return c
    return {'id': c['id'], 'title': c['snippet']['title'],
            'videos': c['statistics'].get('videoCount'), 'uploads': c['contentDetails']['relatedPlaylists']['uploads']}


def main():
    if not KEY:
        raise SystemExit('YT_KEY missing')
    out = {}

    # Hasya Jatra on Sony Marathi
    sm = find_channel(['SonyMarathi', 'sonymarathi'], 'Sony Marathi')
    out['sony_marathi'] = chan_info(sm)
    if 'id' in sm:
        up = sm['contentDetails']['relatedPlaylists']['uploads']
        seen, hits = scan(up, r'hasya\s*jatra|hasyajatra|हास्यजत्रा|हास्य\s*जत्रा')
        out['hasyajatra'] = {'uploads_scanned': seen, **summarize(hits)}

    # CID: start from the playlist Sony links in its descriptions, then its owner channel
    pl = api('playlists', part='snippet,contentDetails', id=CID_PLAYLIST)
    if pl.get('items'):
        p = pl['items'][0]
        out['cid_playlist'] = {'title': p['snippet']['title'], 'owner': p['snippet']['channelTitle'],
                               'channel': p['snippet']['channelId'], 'items': p['contentDetails']['itemCount']}
        seen, hits = scan(CID_PLAYLIST, r'.')
        out['cid_in_playlist'] = {'scanned': seen, **summarize(hits)}
        ch = api('channels', part='snippet,contentDetails,statistics', id=p['snippet']['channelId'])
        if ch.get('items'):
            out['set_india'] = chan_info(ch['items'][0])
            up = ch['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            seen, hits = scan(up, r'\bCID\b')
            out['cid_on_channel'] = {'uploads_scanned': seen, **summarize(hits)}
    else:
        out['cid_playlist'] = {'error': pl.get('error'), 'body': pl.get('body')}

    json.dump(out, open(OUT, 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
