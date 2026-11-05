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
    'hasya': {'name': 'Full episodes', 'sub': 'Numbered episodes, 2018 onwards', 'icon': '😂', 'color': '#b45309', 'voice': 'mr-IN'},
    'hasyamore': {'name': 'Comedy specials', 'sub': 'Compilations and new-season uploads', 'icon': '🎭', 'color': '#9a3412', 'voice': 'mr-IN'},
    'cidnew': {'name': 'New episodes', 'sub': 'CID, Dec 2024 onwards', 'icon': '🕵️', 'color': '#1d4ed8', 'voice': 'hi-IN'},
    'cidold': {'name': 'Older episodes', 'sub': 'CID re-uploads, 2020-2024', 'icon': '🎞️', 'color': '#6d28d9', 'voice': 'hi-IN'},
    'cidclassic': {'name': 'Classic 2013-2018', 'sub': 'CID, opens in YouTube', 'icon': '📼', 'color': '#475569', 'voice': 'hi-IN'},
    # Mummy: Gujarati devotional and wedding songs
    'bhajan': {'name': 'Bhajan', 'sub': 'Devotional songs', 'icon': '🙏', 'color': '#b45309', 'sort': 'pop', 'voice': 'gu-IN'},
    'prabhatiya': {'name': 'Prabhatiya', 'sub': 'Morning songs', 'icon': '🌅', 'color': '#be185d', 'sort': 'pop', 'voice': 'gu-IN'},
    'aarti': {'name': 'Aarti & Chalisa', 'sub': 'Prayers', 'icon': '🪔', 'color': '#92400e', 'sort': 'pop', 'voice': 'gu-IN'},
    'lagna': {'name': 'Lagna Geet', 'sub': 'Wedding songs', 'icon': '💍', 'color': '#b91c1c', 'sort': 'pop', 'voice': 'gu-IN'},
    'dhun': {'name': 'Dhun & Kirtan', 'sub': 'Chanting', 'icon': '🕉️', 'color': '#15803d', 'sort': 'pop', 'voice': 'gu-IN'},
    'dayro': {'name': 'Dayro & Santvani', 'sub': 'Folk bhajans', 'icon': '🎤', 'color': '#1d4ed8', 'sort': 'pop', 'voice': 'gu-IN'},
    'garba': {'name': 'Garba', 'sub': 'Navratri songs', 'icon': '💃', 'color': '#7e22ce', 'sort': 'pop', 'voice': 'gu-IN'},
}
# Home screen tiles per person. A group opens a screen with its own big choices.
PROFILES = {
    'pappa': {'title': 'Pappa TV', 'en': 'Hasya Jatra & CID', 'label': '👨 Pappa', 'color': '#1d4ed8',
              'tiles': [{'group': 'hasya', 'name': 'Hasya Jatra', 'sub': 'Marathi comedy', 'icon': '😂', 'color': '#b45309',
                         'children': ['hasya', 'hasyamore']},
                        {'group': 'cid', 'name': 'CID', 'sub': 'Detective series', 'icon': '🕵️', 'color': '#2f7fd1',
                         'children': ['cidnew', 'cidold', 'cidclassic']}]},
    'mummy': {'title': 'Mummy TV', 'en': 'Bhajan, Lagna Geet & more', 'label': '👩 Mummy', 'color': '#c2410c',
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
        d = api('videos', part='contentDetails,statistics,status,snippet', id=','.join(chunk))
        for v in d.get('items', []):
            title, pub, pl = found[v['id']]
            lib[v['id']] = {
                't': title, 'p': pub, 's': dur(v['contentDetails'].get('duration')),
                'v': int(v.get('statistics', {}).get('viewCount', 0)),
                'e': 1 if v.get('status', {}).get('embeddable') else 0,
            }
            dn = desc_ep(v.get('snippet', {}).get('description'))
            if dn and not episode_no(title):
                lib[v['id']]['n'] = dn
            if tag and pl == tag:
                lib[v['id']]['pl'] = tag
            if kind:
                lib[v['id']]['k'] = kind
    # keep view counts fresh for ones we already know
    known = [v for v in found if v in lib and v not in new]
    for i in range(0, len(known), 50):
        chunk = known[i:i + 50]
        d = api('videos', part='statistics,status,snippet', id=','.join(chunk))
        for v in d.get('items', []):
            dn = desc_ep(v.get('snippet', {}).get('description'))
            if dn and not episode_no(lib[v['id']]['t']) and not lib[v['id']].get('n'):
                lib[v['id']]['n'] = dn
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



# ---------------------------------------------------------------- romanize (Devanagari / Gujarati -> Latin letters)
_V = {'अ': 'a', 'आ': 'a', 'इ': 'i', 'ई': 'i', 'उ': 'u', 'ऊ': 'u', 'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'ऑ': 'o', 'ऍ': 'e'}
_M = {'ा': 'a', 'ि': 'i', 'ी': 'i', 'ु': 'u', 'ू': 'u', 'ृ': 'ri', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ॉ': 'o', 'ॅ': 'e'}
_C = {'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'n', 'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'n',
      'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n', 'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
      'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm', 'य': 'y', 'र': 'r', 'ल': 'l', 'ळ': 'l', 'व': 'v',
      'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h', 'क़': 'q', 'ख़': 'kh', 'ग़': 'g', 'ज़': 'z', 'ड़': 'd', 'ढ़': 'dh', 'फ़': 'f'}
_C.update({'\u0958': 'q', '\u0959': 'kh', '\u095A': 'g', '\u095B': 'z', '\u095C': 'd', '\u095D': 'dh', '\u095E': 'f', '\u095F': 'y'})
_OTHER_DIGITS = {chr(0x966 + i): str(i) for i in range(10)}
_NUQTA = {'क': 'q', 'ख': 'kh', 'ग': 'g', 'ज': 'z', 'ड': 'd', 'ढ': 'dh', 'फ': 'f'}
_OTHER = {**_OTHER_DIGITS, 'ं': 'n', 'ँ': 'n', 'ः': 'h', 'ऽ': '', '।': '.', '॥': '.', '्': ''}
_SCRIPT = re.compile('[\u0900-\u097F\u0A80-\u0AFF]+')


def _rom_word(w, deep=False):
    """w is one run of Devanagari. Returns Latin letters with Hindi/Marathi-style schwa deletion."""
    syl = []          # (consonant_text, vowel_text, explicit)
    i = 0
    while i < len(w):
        ch = w[i]
        if ch in _V:
            syl.append(('', _V[ch], True)); i += 1
        elif ch in _C or ch in ('ऩ', 'ऱ', 'ऴ'):
            c = _C.get(ch, 'n' if ch == 'ऩ' else 'r' if ch == 'ऱ' else 'l')
            i += 1
            if i < len(w) and w[i] == '़':
                c = _NUQTA.get(ch, c); i += 1
            if i < len(w) and w[i] in _M:
                syl.append((c, _M[w[i]], True)); i += 1
            elif i < len(w) and w[i] == '्':
                syl.append((c, '', True)); i += 1          # conjunct: no vowel
            else:
                syl.append((c, 'a', False))                # inherent vowel
        elif ch in _OTHER:
            syl.append((_OTHER[ch], '', True)); i += 1
        else:
            syl.append((ch, '', True)); i += 1
    out = []
    n = len(syl)
    for k, (c, v, explicit) in enumerate(syl):
        if not explicit and v == 'a':
            last = all(x[1] == '' for x in syl[k + 1:])
            prev_explicit = k > 0 and syl[k - 1][2] and syl[k - 1][1] != ''
            nxt = syl[k + 1] if k + 1 < n else None
            nxt_explicit = nxt is not None and nxt[2] and nxt[1] != ''
            prev_ok = prev_explicit or (deep and k > 0 and syl[k - 1][1] != '')
            if last or (prev_ok and nxt_explicit and k > 0):
                v = ''
        out.append(c + v)
    return ''.join(out)


ROMANIZE = False      # titles keep the source's own script; set True to turn Marathi/Hindi/Gujarati into Latin letters


def roman(text):
    if not ROMANIZE:
        return text
    def sub(m):
        run = m.group(0)
        deep = '\u0A80' <= run[0] <= '\u0AFF'          # Gujarati drops more inner a-sounds
        if deep:
            run = ''.join(chr(ord(ch) - 0x180) if '\u0A80' <= ch <= '\u0AFF' else ch for ch in run)
        r = _rom_word(run, deep)
        return r[:1].upper() + r[1:]
    return _SCRIPT.sub(sub, text)


# ---------------------------------------------------------------- classify

DESC_EP = re.compile(r'\b(?:episode|ep)\.?\s*(?:no\.?|number|#)?\s*[:\-]?\s*(\d{1,4})\b', re.I)


def desc_ep(desc):
    m = DESC_EP.search((desc or '')[:600])
    return int(m.group(1)) if m and 0 < int(m.group(1)) < 5000 else 0


def rno(r):
    return episode_no(r['t']) or r.get('n', 0)


def episode_no(t):
    m = EP_RE.search(t)
    return int(m.group(1)) if m else 0


def show_of(r):
    t = r['t']
    if HJ_RE.search(t):
        if not (r['e'] and r['s'] >= 2100):
            return None
        return 'hasya' if rno(r) else 'hasyamore'
    if CID_RE.search(t):
        if r['s'] < 1200:
            return None
        if r['p'] >= NEW_CID_FROM:
            return 'cidnew' if r['s'] >= 1500 else None
        return 'cidold' if r['e'] else 'cidclassic'
    return None


DATE_RE = re.compile(r'^\d{1,2}(st|nd|rd|th)?\s+\w+,?\s+\d{4}$|^\d{1,2}\s+\w{3}\s+\d{4}$', re.I)
NOISE_RE = re.compile(r'^cid\s*\(.*\)(\s*season\s*\d+)?$|^season\s*\d+$|full episode|^cid$|^c\.i\.d$|सीआईडी$|सीआयडी$|sign up for sony liv|^new season$|^best comedy$|^thrilling cases$', re.I)


def clean_title(t, show, extra=0):
    n = episode_no(t)
    if re.search(r'\s-\s', t) and n:
        segs = [x.strip() for x in re.split(r'\s+-\s+', t)]
        keep = [x for x in segs if x and not NOISE_RE.search(x) and not HJ_RE.search(x) and not CID_RE.fullmatch(x)
                and not DATE_RE.match(x) and not EP_RE.fullmatch(x)]
        return ('Ep %d' % n) + (roman(' — ' + ' — '.join(keep)) if keep else '')
    parts = [x.strip() for x in re.split(r'\s*[|]\s*', t) if x.strip()]
    parts = [x for x in parts if not NOISE_RE.search(x) and not HJ_RE.search(x) and not CID_RE.fullmatch(x)]
    head = parts[0] if parts else t
    return roman(head[:110])


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
        return roman(t[:100].strip())
    head = parts[0]
    if len(parts) > 1 and len(parts[1]) < 40 and not re.search(r'bhajan|gujarati|song|geet|aarti|dhun|garba|new|latest|hd|ભજન', parts[1], re.I):
        head += ' — ' + parts[1]
    return roman(head[:110])


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
    for k in ('hasya', 'hasyamore', 'cidnew', 'cidold'):
        groups[k] = dedupe(groups[k])
    out = {}
    for s, rows in groups.items():
        if s in MUMMY_CATS:
            rows = dedupe_songs(rows)[:MUMMY_LIMIT]
            out[s] = [[r['id'], clean_song(r['t']), r['p'], round(r['s'] / 60), 0, 0, 0, r['v']] for r in rows]
            continue
        if s in ('cidold', 'cidclassic'):
            rows.sort(key=lambda r: (rno(r) == 0, rno(r), r['p']))
        else:
            rows.sort(key=lambda r: (r['p'], rno(r)), reverse=True)
        out[s] = [[r['id'], clean_title(r['t'], s), r['p'], round(r['s'] / 60), rno(r),
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
               'orientation': 'portrait', 'background_color': '#f6f3ec', 'theme_color': '#f6f3ec',
               'icons': [{'src': 'icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
                         {'src': 'icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'}]},
              open(os.path.join(folder, 'manifest.webmanifest'), 'w'), ensure_ascii=False)
    make_icons(folder, color)


HOME = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f6f3ec">
<title>Family TV</title><link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="icon-192.png">
<style>
body{margin:0;background:#f6f3ec;color:#16181d;font:22px system-ui,-apple-system,"Noto Sans Devanagari","Noto Sans Gujarati",sans-serif;padding:18px}
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
