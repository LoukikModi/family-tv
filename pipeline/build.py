"""Build the family TV site.

  python pipeline/build.py quick   # newest uploads only (cheap, for frequent runs)
  python pipeline/build.py full    # deep scan of channels + playlists (daily / on push)

Reads the YouTube Data API (env YT_KEY), keeps everything in data/library.json,
and writes the static site into public/. Standard library + Pillow (icons only).
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, 'data', 'library.json')
PUB = os.path.join(ROOT, 'public')
TEMPLATE = os.path.join(ROOT, 'web', 'app.html')
KEY = os.environ.get('YT_KEY', '')

SONY_MARATHI = 'UC1VShXGomrvEyn60Klc2i7Q'
SET_INDIA = 'UCpEhnqL0y41EpW2TvWAHD7Q'
CID_PLAYLIST = 'PLzufeTFnhupxVg-1DHmZAsaWLZ_kKPNRh'      # Sony's own "CID full episodes" playlist
NEW_CID_FROM = '2024-12-21'                              # CID Season 2 premiere

HJ_RE = re.compile(r'hasya\s*jatra|hasyajatra|हास्यजत्रा|हास्य\s*जत्रा', re.I)
CID_RE = re.compile(r'\bC\.?I\.?D\b|सीआईडी|सीआयडी', re.I)
EP_RE = re.compile(r'\b(?:ep|episode)s?\.?\s*(\d{1,4})\b', re.I)

# What each person sees. Mummy's page can be added here later.
SHOWS = {
    'hasya': {'mr': 'महाराष्ट्राची हास्यजत्रा', 'en': 'Hasya Jatra', 'icon': '😂', 'color': '#e8a317'},
    'cidnew': {'mr': 'सीआयडी — नवीन', 'en': 'CID new episodes', 'icon': '🕵️', 'color': '#2f7fd1'},
    'cidold': {'mr': 'सीआयडी — जुने', 'en': 'CID older episodes', 'icon': '🎞️', 'color': '#7b5ea7'},
    'cidclassic': {'mr': 'सीआयडी — सर्वात जुने', 'en': 'CID classic 2013-2018 (opens in YouTube)', 'icon': '📼', 'color': '#5d6d7e'},
}
PROFILES = {
    'dad': {'title': 'आपला टीव्ही', 'en': 'Our TV', 'shows': ['hasya', 'cidnew', 'cidold', 'cidclassic']},
}


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
            if ex.code == 404:
                return {'items': []}
            if ex.code in (400, 401, 403):
                raise SystemExit('YouTube API error %s: %s' % (ex.code, body[:300]))
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return {'items': []}


def dur(s):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', s or '')
    if not m:
        return 0
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se


def playlist_items(pid, pages):
    token = ''
    for _ in range(pages):
        d = api('playlistItems', part='snippet,contentDetails', playlistId=pid, maxResults=50, pageToken=token)
        for it in d.get('items', []):
            sn = it['snippet']
            vid = it['contentDetails'].get('videoId') or sn.get('resourceId', {}).get('videoId')
            title = sn.get('title', '')
            if not vid or title in ('Private video', 'Deleted video'):
                continue
            yield vid, title, (it['contentDetails'].get('videoPublishedAt') or sn.get('publishedAt', ''))[:10]
        token = d.get('nextPageToken', '')
        if not token:
            break


def channel_playlists(cid, title_re, pages=30):
    token, out = '', []
    for _ in range(pages):
        d = api('playlists', part='snippet', channelId=cid, maxResults=50, pageToken=token)
        for it in d.get('items', []):
            if title_re.search(it['snippet'].get('title', '')):
                out.append(it['id'])
        token = d.get('nextPageToken', '')
        if not token:
            break
    return out


def collect(lib, wanted, source_playlists, title_re, upload_pages, playlist_pages, tag=None):
    """Find candidate videos by title, then fetch their durations/embeddability."""
    found = {}
    for pl, pages in source_playlists:
        for vid, title, pub in playlist_items(pl, pages):
            if title_re.search(title):
                found[vid] = (title, pub, pl)
    new = [v for v in found if v not in lib or 'e' not in lib[v]]
    for i in range(0, len(new), 50):
        chunk = new[i:i + 50]
        d = api('videos', part='contentDetails,statistics,status', id=','.join(chunk))
        for v in d.get('items', []):
            title, pub, pl = found[v['id']]
            lib[v['id']] = {
                't': title, 'p': pub, 's': dur(v['contentDetails'].get('duration')),
                'v': int(v.get('statistics', {}).get('viewCount', 0)),
                'e': 1 if v.get('status', {}).get('embeddable') else 0,
            }
            if tag and pl == tag:
                lib[v['id']]['pl'] = tag
    # keep view counts fresh for ones we already know
    known = [v for v in found if v in lib and v not in new]
    for i in range(0, len(known), 50):
        chunk = known[i:i + 50]
        d = api('videos', part='statistics,status', id=','.join(chunk))
        for v in d.get('items', []):
            lib[v['id']]['v'] = int(v.get('statistics', {}).get('viewCount', 0))
            lib[v['id']]['e'] = 1 if v.get('status', {}).get('embeddable') else 0
            if tag and found[v['id']][2] == tag:
                lib[v['id']]['pl'] = tag
    return len(found)


def fetch(lib, mode):
    deep = mode == 'full'
    up_pages = 400 if deep else 4
    # Hasya Jatra on Sony Marathi
    sources = [('UU' + SONY_MARATHI[2:], up_pages)]
    if deep:
        sources += [(p, 60) for p in channel_playlists(SONY_MARATHI, HJ_RE)]
    n1 = collect(lib, None, sources, HJ_RE, up_pages, 60)
    # CID on SET India
    sources = [('UU' + SET_INDIA[2:], up_pages), (CID_PLAYLIST, 60)]
    if deep:
        sources += [(p, 60) for p in channel_playlists(SET_INDIA, CID_RE) if p != CID_PLAYLIST]
    n2 = collect(lib, None, sources, CID_RE, up_pages, 60, tag=CID_PLAYLIST)
    print('candidates: hasya-ish %d, cid-ish %d, library %d' % (n1, n2, len(lib)))


# ---------------------------------------------------------------- classify

def episode_no(t):
    m = EP_RE.search(t)
    return int(m.group(1)) if m else 0


def show_of(r):
    t = r['t']
    if HJ_RE.search(t):
        return 'hasya' if r['e'] and r['s'] >= 2100 else None
    if CID_RE.search(t):
        if r['s'] < 1200:
            return None
        if r['p'] >= NEW_CID_FROM:
            return 'cidnew' if r['s'] >= 1500 else None
        return 'cidold' if r['e'] else 'cidclassic'
    return None


DATE_RE = re.compile(r'^\d{1,2}(st|nd|rd|th)?\s+\w+,?\s+\d{4}$|^\d{1,2}\s+\w{3}\s+\d{4}$', re.I)
NOISE_RE = re.compile(r'full episode|^cid$|^c\.i\.d$|सीआईडी$|सीआयडी$|sign up for sony liv|^new season$|^best comedy$|^thrilling cases$', re.I)


def clean_title(t, show):
    n = episode_no(t)
    if re.search(r'\s-\s', t) and n:
        segs = [x.strip() for x in re.split(r'\s+-\s+', t)]
        keep = [x for x in segs if x and not NOISE_RE.search(x) and not HJ_RE.search(x) and not CID_RE.fullmatch(x)
                and not DATE_RE.match(x) and not EP_RE.fullmatch(x)]
        return ('भाग %d' % n) + (' — ' + ' — '.join(keep) if keep else '')
    parts = [x.strip() for x in re.split(r'\s*[|]\s*', t) if x.strip()]
    parts = [x for x in parts if not NOISE_RE.search(x) and not HJ_RE.search(x) and not CID_RE.fullmatch(x)]
    head = parts[0] if parts else t
    return head[:110]


def dedupe(rows):
    """Sony uploads many episodes twice (Hindi/Marathi and English title). Keep the one with most views."""
    rows = sorted(rows, key=lambda r: -r['v'])
    kept, by_day = [], {}
    for r in rows:
        day = int(r['p'].replace('-', '')) if r['p'] else 0
        near = [k for d in (day - 1, day, day + 1) for k in by_day.get(d, [])]
        if any(abs(r['s'] - k['s']) <= 8 for k in near):
            continue
        kept.append(r)
        by_day.setdefault(day, []).append(r)
    return kept


def select(lib):
    groups = {k: [] for k in SHOWS}
    for vid, r in lib.items():
        if 'e' not in r:
            continue
        s = show_of(r)
        if s:
            groups[s].append(dict(r, id=vid))
    for k in ('hasya', 'cidnew', 'cidold'):
        groups[k] = dedupe(groups[k])
    out = {}
    for s, rows in groups.items():
        if s in ('cidold', 'cidclassic'):
            rows.sort(key=lambda r: (episode_no(r['t']) == 0, episode_no(r['t']), r['p']))
        else:
            rows.sort(key=lambda r: (r['p'], episode_no(r['t'])), reverse=True)
        out[s] = [[r['id'], clean_title(r['t'], s), r['p'], round(r['s'] / 60), episode_no(r['t']),
                   0 if r['e'] else 1, 1 if r.get('pl') else 0, r['v']] for r in rows]
    return out


# ---------------------------------------------------------------- site

def make_icons(folder, color):
    from PIL import Image, ImageDraw
    for size in (192, 512):
        im = Image.new('RGB', (size, size), color)
        d = ImageDraw.Draw(im)
        m = size * 0.22
        d.rounded_rectangle([m, m * 1.1, size - m, size - m * 1.1], radius=size * 0.08, outline='white', width=int(size * 0.045))
        d.polygon([(size * .43, size * .36), (size * .43, size * .64), (size * .67, size * .5)], fill='white')
        im.save(os.path.join(folder, 'icon-%d.png' % size))


def write_site(shows):
    tpl = open(TEMPLATE, encoding='utf-8').read()
    os.makedirs(PUB, exist_ok=True)
    for pid, prof in PROFILES.items():
        folder = os.path.join(PUB, pid)
        os.makedirs(folder, exist_ok=True)
        data = {'profile': pid, 'title': prof['title'], 'en': prof['en'], 'cidPlaylist': CID_PLAYLIST,
                'shows': [dict(SHOWS[k], key=k, items=shows[k]) for k in prof['shows']]}
        html = tpl.replace('/*DATA*/null', json.dumps(data, ensure_ascii=False, separators=(',', ':')))
        html = html.replace('__TITLE__', prof['title'])
        open(os.path.join(folder, 'index.html'), 'w', encoding='utf-8').write(html)
        json.dump({'name': prof['title'], 'short_name': prof['title'], 'start_url': './', 'scope': './',
                   'display': 'standalone', 'orientation': 'portrait', 'background_color': '#101418',
                   'theme_color': '#101418',
                   'icons': [{'src': 'icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
                             {'src': 'icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'}]},
                  open(os.path.join(folder, 'manifest.webmanifest'), 'w'), ensure_ascii=False)
        make_icons(folder, '#c0392b')
    home = ['<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">',
            '<title>Family TV</title><body style="font:28px sans-serif;background:#101418;color:#fff;margin:0;padding:24px">',
            '<h1>Family TV</h1>']
    for pid, prof in PROFILES.items():
        home.append('<p><a style="display:block;padding:28px;background:#c0392b;color:#fff;border-radius:18px;text-decoration:none" href="%s/">%s</a></p>' % (pid, prof['title']))
    open(os.path.join(PUB, 'index.html'), 'w', encoding='utf-8').write('\n'.join(home))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'quick'
    old = open(LIB, 'rb').read() if os.path.exists(LIB) else b''
    lib = json.loads(old) if old else {}
    if KEY:
        try:
            fetch(lib, mode)
        except Quota:
            print('quota exhausted, using what we have')
    elif not lib:
        raise SystemExit('YT_KEY missing and no data/library.json')
    shows = select(lib)
    for k, v in shows.items():
        print('%s: %d' % (k, len(v)))
    write_site(shows)
    new = json.dumps(lib, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()
    changed = new != old
    if changed:
        os.makedirs(os.path.dirname(LIB), exist_ok=True)
        open(LIB, 'wb').write(new)
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        open(out, 'a').write('changed=%s\n' % ('true' if changed else 'false'))


if __name__ == '__main__':
    main()
