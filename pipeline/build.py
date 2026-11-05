"""Build the family TV site.

  python pipeline/build.py quick   # newest uploads only (cheap, for frequent runs)
  python pipeline/build.py full    # deep scan of channels + playlists (daily / on push)

Reads the YouTube Data API (env YT_KEY), keeps everything in data/library.json,
and writes the static site into public/. Standard library + Pillow (icons only).
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, 'data', 'library.json')
STATE = os.path.join(ROOT, 'data', 'state.json')
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

# What each person sees. Add more people / categories here.
SHOWS = {
    'hasya': {'name': 'Hasya Jatra', 'sub': 'Maharashtrachi HasyaJatra', 'icon': '😂', 'color': '#e8a317'},
    'cidnew': {'name': 'New episodes', 'sub': 'CID, Dec 2024 onwards', 'icon': '🕵️', 'color': '#2f7fd1'},
    'cidold': {'name': 'Older episodes', 'sub': 'CID re-uploads, 2020-2024', 'icon': '🎞️', 'color': '#7b5ea7'},
    'cidclassic': {'name': 'Classic 2013-2018', 'sub': 'CID, opens in YouTube', 'icon': '📼', 'color': '#5d6d7e'},
    # Mummy: Gujarati devotional and wedding songs
    'bhajan': {'name': 'Bhajan', 'sub': 'Devotional songs', 'icon': '🙏', 'color': '#d9822b', 'sort': 'pop'},
    'prabhatiya': {'name': 'Prabhatiya', 'sub': 'Morning songs', 'icon': '🌅', 'color': '#c0587a', 'sort': 'pop'},
    'aarti': {'name': 'Aarti & Chalisa', 'sub': 'Prayers', 'icon': '🪔', 'color': '#b8860b', 'sort': 'pop'},
    'lagna': {'name': 'Lagna Geet', 'sub': 'Wedding songs', 'icon': '💍', 'color': '#c0392b', 'sort': 'pop'},
    'dhun': {'name': 'Dhun & Kirtan', 'sub': 'Chanting', 'icon': '🕉️', 'color': '#2e8b57', 'sort': 'pop'},
    'dayro': {'name': 'Dayro & Santvani', 'sub': 'Folk bhajans', 'icon': '🎤', 'color': '#2f7fd1', 'sort': 'pop'},
    'garba': {'name': 'Garba', 'sub': 'Navratri songs', 'icon': '💃', 'color': '#8e44ad', 'sort': 'pop'},
}
# Home screen tiles per person. A group opens a screen with its own big choices.
PROFILES = {
    'pappa': {'title': 'Pappa TV', 'en': 'Hasya Jatra & CID', 'label': '👨 Pappa', 'color': '#2f7fd1',
              'tiles': [{'show': 'hasya'},
                        {'group': 'cid', 'name': 'CID', 'sub': 'Detective series', 'icon': '🕵️', 'color': '#2f7fd1',
                         'children': ['cidnew', 'cidold', 'cidclassic']}]},
    'mummy': {'title': 'Mummy TV', 'en': 'Bhajan, Lagna Geet & more', 'label': '👩 Mummy', 'color': '#e67e22',
              'tiles': [{'show': k} for k in ('bhajan', 'prabhatiya', 'aarti', 'lagna', 'dhun', 'dayro', 'garba')]},
}

# Official Gujarati labels / channels scanned for Mummy's page
MUMMY_CHANNELS = [
    'UCcmYmr96fmCrV3bjEkjrKYA',  # Soor Mandir
    'UCBdyt1Dw71b_feHr7nnjCjQ',  # Soor Mandir Audio Jukebox
    'UCuB7zkQVpcPKzHYJn45vM9w',  # RDC Gujarati
    'UCgR_i5SKxLHWGCFYPQ3LDNw',  # RDC Bhakti Sagar
    'UCQiT5-5LOEyhN2Q1g93ZmRA',  # Studio Sangeeta
    'UCpZVXyR7lix525VPi3Vc5mg',  # Studio Saraswati Official
    'UCev6abkwjdHj_dB3rquFfbQ',  # T-Series Gujarati
    'UC15sUwufvfo5Z62KBZVzHRQ',  # Ram Audio
    'UCqfu1RJHPXG0PIslUsCkb0A',  # Ashok Sound
    'UCQJLc3UGESs_l8Pe5F7bdCw',  # Sur Sagar Music
    'UCfOF7Jw4GfLK9BvAlZ9Vvww',  # KD Digital (Kinjal Dave)
    'UCrChDgWamU1TgliBNsMYwOQ',  # Gujarati Bhakti Sagar
    'UCxEjIcW9n0JsTSCGQDufi9A',  # Geeta Rabari
    'UCW8BWcgpCtPRG3nLSGLAK2g',  # IVY Meshwa Films
    'UC3rHdnHlSdEDX7M67hxwCew',  # Worldwide Records Gujarati
]
# First match wins (most specific first). Title keywords in Gujarati script and Latin spelling.
CATS = [
    ('lagna', r'lagna|lagan|laggeet|લગ્ન|લગન|વિવાહ|vivah|vidai|વિદાય|pithi|પીઠી|mandvo|મંડપ|ફેરા|wedding|marriage|સીમંત'),
    ('prabhatiya', r'prabhatiy|પ્રભાતિયા|morning bhajan'),
    ('aarti', r'aarti|\barti\b|આરતી|stuti|સ્તુતિ|chalisa|chalisha|ચાલીસા'),
    ('dhun', r'dhun|ધૂન|kirtan|કીર્તન|jaap|જાપ|mantra|મંત્ર'),
    ('dayro', r'dayro|dayra|ડાયરો|santvani|સંતવાણી|bhajan sandhya|ભજન સંધ્યા|satsang|સત્સંગ|katha|કથા'),
    ('garba', r'garba|ગરબા|dandiya|navratri|નવરાત્રી'),
    ('bhajan', r'bhajan|ભજન|bhakti|ભક્તિ|devotional|krishna|કૃષ્ણ|hanuman|હનુમાન|mahadev|મહાદેવ|\bshiv\b|શિવ|ambe|માતાજી|mataji|ganesh|ગણેશ|swaminarayan|સ્વામિનારાયણ|ramdev|રામદેવ|shrinathji|dwarkadhish|દ્વારકા'),
]
CAT_RE = [(k, re.compile(v, re.I)) for k, v in CATS]
MUMMY_ANY = re.compile('|'.join(v for _, v in CATS), re.I)
MUMMY_BAD = re.compile(r'comedy|jokes|\bdj\b|remix|mashup|full movie|trailer|natak|\bnonstop comedy', re.I)
MUMMY_LIMIT = 800          # keep the best-viewed videos per category so the page stays light


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


def collect(lib, wanted, source_playlists, title_re, upload_pages, playlist_pages, tag=None, kind=None):
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
            if kind:
                lib[v['id']]['k'] = kind
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


def pages_for(state, key, mode):
    """Deep scan a source once (or when asked); afterwards only look at the newest uploads."""
    if mode == 'deep' or not state['deep'].get(key):
        return 400, True
    return (40 if mode == 'full' else 4), False


def fetch(lib, state, mode):
    done = lambda key, deep: deep and state['deep'].__setitem__(key, True)
    # Hasya Jatra on Sony Marathi
    n, deep = pages_for(state, 'sony_marathi', mode)
    sources = [('UU' + SONY_MARATHI[2:], n)]
    if deep:
        sources += [(p, 60) for p in channel_playlists(SONY_MARATHI, HJ_RE)]
    n1 = collect(lib, None, sources, HJ_RE, n, 60)
    done('sony_marathi', deep)
    # CID on SET India
    n, deep = pages_for(state, 'set_india', mode)
    sources = [('UU' + SET_INDIA[2:], n), (CID_PLAYLIST, 60)]
    if deep:
        sources += [(p, 60) for p in channel_playlists(SET_INDIA, CID_RE) if p != CID_PLAYLIST]
    n2 = collect(lib, None, sources, CID_RE, n, 60, tag=CID_PLAYLIST)
    done('set_india', deep)
    # Mummy: Gujarati devotional / wedding songs, one channel at a time so progress is kept
    n3 = 0
    for c in MUMMY_CHANNELS:
        n, deep = pages_for(state, c, mode)
        n3 += collect(lib, None, [('UU' + c[2:], n)], MUMMY_ANY, n, 60, kind='m')
        done(c, deep)
    print('candidates: hasya-ish %d, cid-ish %d, mummy-ish %d, library %d' % (n1, n2, n3, len(lib)))


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
NOISE_RE = re.compile(r'^cid\s*\(.*\)(\s*season\s*\d+)?$|^season\s*\d+$|full episode|^cid$|^c\.i\.d$|सीआईडी$|सीआयडी$|sign up for sony liv|^new season$|^best comedy$|^thrilling cases$', re.I)


def clean_title(t, show):
    n = episode_no(t)
    if re.search(r'\s-\s', t) and n:
        segs = [x.strip() for x in re.split(r'\s+-\s+', t)]
        keep = [x for x in segs if x and not NOISE_RE.search(x) and not HJ_RE.search(x) and not CID_RE.fullmatch(x)
                and not DATE_RE.match(x) and not EP_RE.fullmatch(x)]
        return ('Ep %d' % n) + (' — ' + ' — '.join(keep) if keep else '')
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


MUMMY_CATS = [k for k, _ in CATS]
SONG_NOISE = re.compile(r'full video|hd video|new gujarati|latest gujarati|official|audio|video song|gujarati song|full hd|superhit|2\d{3}$|^song of faith', re.I)


def song_cat(r):
    t = r['t']
    if not r['e'] or r['s'] < 150 or r['s'] > 3 * 3600 or MUMMY_BAD.search(t):
        return None
    for k, rx in CAT_RE:
        if rx.search(t):
            return k
    return None


def clean_song(t):
    t = re.sub(r'#\S+', '', t)
    t = re.sub(r'@\S+', '', t)
    parts = [x.strip(' -|') for x in t.split('|')]
    parts = [x for x in parts if x and not SONG_NOISE.search(x)]
    if not parts:
        return t[:100].strip()
    head = parts[0]
    if len(parts) > 1 and len(parts[1]) < 40 and not re.search(r'bhajan|gujarati|song|geet|aarti|dhun|garba|new|latest|hd|ભજન', parts[1], re.I):
        head += ' — ' + parts[1]
    return head[:110]


def dedupe_songs(rows):
    best = {}
    for r in rows:
        key = re.sub(r'[\W_]+', '', clean_song(r['t']).lower())[:48]
        if key not in best or r['v'] > best[key]['v']:
            best[key] = r
    return sorted(best.values(), key=lambda r: -r['v'])


def select(lib):
    groups = {k: [] for k in SHOWS}
    for vid, r in lib.items():
        if 'e' not in r:
            continue
        if r.get('k') == 'm':
            c = song_cat(r)
            if c:
                groups[c].append(dict(r, id=vid))
            continue
        s = show_of(r)
        if s:
            groups[s].append(dict(r, id=vid))
    for k in ('hasya', 'cidnew', 'cidold'):
        groups[k] = dedupe(groups[k])
    out = {}
    for s, rows in groups.items():
        if s in MUMMY_CATS:
            rows = dedupe_songs(rows)[:MUMMY_LIMIT]
            out[s] = [[r['id'], clean_song(r['t']), r['p'], round(r['s'] / 60), 0, 0, 0, r['v']] for r in rows]
            continue
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


def write_manifest(folder, name, color):
    json.dump({'name': name, 'short_name': name, 'start_url': './', 'scope': './', 'display': 'standalone',
               'orientation': 'portrait', 'background_color': '#101418', 'theme_color': '#101418',
               'icons': [{'src': 'icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
                         {'src': 'icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'}]},
              open(os.path.join(folder, 'manifest.webmanifest'), 'w'), ensure_ascii=False)
    make_icons(folder, color)


HOME = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#101418">
<title>Family TV</title><link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="icon-192.png">
<style>
body{margin:0;background:#101418;color:#fff;font:22px system-ui,-apple-system,"Noto Sans Devanagari","Noto Sans Gujarati",sans-serif;padding:18px}
h1{font-size:1.3rem;margin:6px 4px 14px}
a{display:flex;flex-direction:column;justify-content:center;min-height:38vh;margin:14px 0;padding:22px;border-radius:26px;color:#fff;text-decoration:none;font-weight:800;font-size:2rem}
a small{font-size:1rem;font-weight:600;opacity:.92}
a:active{filter:brightness(1.25)}
</style></head><body><h1>Family TV</h1>
%s
</body></html>"""


def write_site(shows):
    tpl = open(TEMPLATE, encoding='utf-8').read()
    os.makedirs(PUB, exist_ok=True)
    tiles = []
    for pid, prof in PROFILES.items():
        folder = os.path.join(PUB, pid)
        os.makedirs(folder, exist_ok=True)
        keys = []
        for t in prof['tiles']:
            keys += t.get('children') or [t['show']]
        data = {'profile': pid, 'title': prof['title'], 'cidPlaylist': CID_PLAYLIST, 'tiles': prof['tiles'],
                'shows': [dict(SHOWS[k], key=k, items=shows[k]) for k in keys]}
        html = tpl.replace('/*DATA*/null', json.dumps(data, ensure_ascii=False, separators=(',', ':')))
        html = html.replace('__TITLE__', prof['title'])
        open(os.path.join(folder, 'index.html'), 'w', encoding='utf-8').write(html)
        write_manifest(folder, prof['title'], prof['color'])
        tiles.append('<a style="background:%s" href="%s/">%s<small>%s</small></a>' % (
            prof['color'], pid, prof['label'], prof['en']))
    open(os.path.join(PUB, 'index.html'), 'w', encoding='utf-8').write(HOME % '\n'.join(tiles))
    write_manifest(PUB, 'Family TV', '#c0392b')
    # old address from the first version still works
    os.makedirs(os.path.join(PUB, 'dad'), exist_ok=True)
    open(os.path.join(PUB, 'dad', 'index.html'), 'w').write(
        '<!doctype html><meta charset=utf-8><meta http-equiv=refresh content="0;url=../pappa/"><a href="../pappa/">Pappa</a>')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'quick'      # rebuild | quick | full | deep
    old = open(LIB, 'rb').read() if os.path.exists(LIB) else b''
    lib = json.loads(old) if old else {}
    old_state = open(STATE, 'rb').read() if os.path.exists(STATE) else b''
    state = json.loads(old_state) if old_state else {}
    state.setdefault('deep', {})
    if KEY and mode != 'rebuild':
        try:
            fetch(lib, state, mode)
            state['quota_hit'] = False
        except Quota:
            state['quota_hit'] = True
            print('quota exhausted, using what we have')
    elif not lib:
        raise SystemExit('YT_KEY missing and no data/library.json')
    shows = select(lib)
    for k, v in shows.items():
        print('%s: %d' % (k, len(v)))
    write_site(shows)
    new = json.dumps(lib, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()
    new_state = json.dumps(state, indent=1, sort_keys=True).encode()
    changed = new != old or new_state != old_state
    if changed:
        os.makedirs(os.path.dirname(LIB), exist_ok=True)
        open(LIB, 'wb').write(new)
        open(STATE, 'wb').write(new_state)
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        open(out, 'a').write('changed=%s\n' % ('true' if changed else 'false'))


if __name__ == '__main__':
    main()
