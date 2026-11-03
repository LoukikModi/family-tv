"""Labeling + site-building logic for TMKOC Tube (standard library only)."""
import bisect, collections, json, re, statistics
from datetime import date

CH = {'Jethalal': r'jetha|जेठा|\bjethiya', 'Bhide': r'bhide|भिड़े|भिडे', 'Daya': r'\bdaya\b|dayaben|दया', 'Popatlal': r'popat|पोपट', 'Tapu Sena': r'tapu|टप्पू|\bgoli\b|\bgogi\b|pinku|\bsonu\b|tapusena|tappu', 'Babita': r'babita|बबिता', 'Iyer': r'\biyer|अय्यर', 'Sodhi': r'sodhi|\broshan|सोढ़ी|सोढी|rosesh', 'Taarak': r'\btaarak\b|तारक|\btarak\b', 'Anjali': r'anjali|अंजली', 'Madhavi': r'madhavi|माधवी', 'Bapuji': r'bapuji|champaklal|चंपक|बापूजी|\bchampak', 'Natu Kaka': r'natu|bagha|नट्टू|बाघा|\bbawri', 'Abdul': r'\babdul|अब्दुल', 'Dr. Hathi': r'hathi|हाथी', 'Komal': r'komal|कोमल', 'Chalu Pandey': r'chalu|pandey|चालू'}
TH = {'Festivals': r'\b(holi|diwali|ganpati|ganesh|bappa|navratri|garba|raksha ?bandhan|rakhi|janmashtami|dahi handi|christmas|new year|eid|dussehra|ravan|independence day|republic day|lohri|sankranti|halloween|karva chauth|ugadi|durga|festival|utsav)\b|होली|दिवाली|गणपति|त्योहार', 'Wedding & Romance': r'\b(wedding|shaadi|marriage|engagement|bride|groom|bulbul|sagai|valentine|honeymoon|anniversary)\b|शादी|विवाह|सगाई', 'Ghost & Horror': r'\b(ghost|bhoot|bhootni|haunted|horror|spooky|witch|chudail)\b|भूत|चुड़ैल', 'Cricket & Sports': r'\b(cricket|gpl|premier league|bat|kabaddi|football|sports?|trophy|tournament|batting|bowling)\b|क्रिकेट', 'Trips & Picnic': r'\b(picnic|trip|tour|vacation|travel|journey|train|flight|airport|goa|jungle|camping|safari|road ?trip)\b|पिकनिक', 'Society Drama': r'\b(maintenance|secretary|committee|mahila mandal|purush mandali|election|meeting|chairman)\b|मीटिंग|सोसाइटी की', 'Mystery & Chaos': r'\b(mystery|missing|kidnap\w*|thief|theft|robbery|stolen|police|detective|spy|burglar|culprit|investigation)\b|चोरी|लापता', 'Money & Business': r'\b(shop|gada electronics|investment|invest|lottery|loan|scam|fraud|profit|customer|bank|salary|discount|business)\b|दुकान', 'Husband vs Wife': r'\b(husbands?|wives|biwi|patni|mahila mandal)\b|पत्नी|बीवी', 'Kids & School': r'\b(school|exam|teacher|homework|college|students?|children|kids|result)\b|स्कूल|बच्चे', 'Food & Cooking': r'\b(food|cook|cooking|recipe|jalebi|fafda|dhokla|chai|tea|ice cream|pizza|thali|samosa|mithai|restaurant|ladoo|lunch|dinner|sweets?)\b|खाना', 'Journalism': r'\b(patrakar|reporter|journalist|interview|news channel)\b|पत्रकार', 'Tech & Gadgets': r'\b(mobile|smartphone|whatsapp|instagram|reels?|laptop|robot|video call|selfie|app|online|internet|camera)\b', 'Health & Doctor': r'\b(doctor|hospital|medicine|fever|injury|treatment|dentist|fitness|diet|yoga|gym|ill|sick)\b'}
CHN, THN = list(CH), list(TH)
CRX = [re.compile(v, re.I) for v in CH.values()]
TRX = [re.compile(v, re.I) for v in TH.values()]
SHOW = re.compile(r'taarak mehta k[ao] oo?lt?[ah]+ chash?mah|tmkoc|तारक मेहता का उल्टा चश्मा|taarak mehta ka chashmah', re.I)
EP_TITLE = re.compile(r'\b(?:ep|episode)s?\.?\s*(\d{1,4})', re.I)
EP_DESC = re.compile(r'\bepisode\s*(?:no\.?)?\s*[:#\-]?\s*(\d{1,4})\b|\bep\.?\s*(?:no\.?)?\s*[:#\-]?\s*(\d{3,4})\b', re.I)
WEEKLY = re.compile(r'weekly\s*reliv', re.I)


def seconds(d):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', d)
    h, mi, s = [int(x or 0) for x in m.groups()]
    return h * 3600 + mi * 60 + s


def plot(desc):
    out = []
    for l in (l.strip() for l in desc.split('\n')):
        if not l or re.search(r'https?://|click here|subscribe|download|show name|^#|follow us|watch (full|more)|sony liv|©|^-+$|^episode\s*\d+\s*[:\-–]*\s*-*$', l, re.I):
            continue
        l = re.sub(r'^episode\s*\d+\s*[:\-–]+\s*-*\s*', '', l, flags=re.I).strip(' -–:')
        if len(l) > 25:
            out.append(l)
    return ' '.join(out)[:600]


def ingest(raw, playlist_titles=()):
    """Raw YouTube video record -> compact site record, or None if it does not belong on the site."""
    if not raw.get('embeddable', True):
        return None
    s = seconds(raw['duration'])
    t, tl = raw['title'], raw['title'].lower()
    if s < 900 or WEEKLY.search(tl):
        return None
    if 'full movie' in tl:
        kind = 'movie'
    elif (re.search(r'\b(ep|episode)s?\.?\s*\d{1,4}', tl) or 'full episode' in tl) and s <= 2700:
        kind = 'episode'
    else:
        return None
    e = None
    if kind == 'episode':
        m = EP_TITLE.search(t)
        if m:
            e = int(m.group(1))
        else:
            m = EP_DESC.search(raw.get('description', '')) or EP_DESC.search(' '.join(raw.get('tags', [])))
            if m:
                e = int(m.group(1) or m.group(2))
    p = plot(raw.get('description', ''))
    txt = SHOW.sub(' ', t + ' . ' + p[:220])
    pl = SHOW.sub(' ', ' '.join(playlist_titles))
    return {'id': raw['id'], 't': t, 'p': raw['published'][:10], 's': s, 'v': raw['views'], 'l': raw['likes'],
            'k': kind, 'e': e,
            'c': [i for i, r in enumerate(CRX) if r.search(txt)],
            'h': [i for i, r in enumerate(TRX) if r.search(txt + ' ' + pl)],
            'd': p}


def _ord(p):
    return date.fromisoformat(p).toordinal()


def build(videos):
    """List of site records -> bundle for the web page (estimates numbers, scores quality, merges duplicates)."""
    data = [dict(v) for v in videos]
    for o in data:
        o['x'] = 0
    # estimate missing episode numbers from neighbours by upload date (flagged x=1)
    nums = sorted((_ord(o['p']), o['e']) for o in data if o['k'] == 'episode' and o['e'])
    ds = [d for d, _ in nums]
    for o in data:
        if o['k'] == 'episode' and o['e'] is None:
            d0 = _ord(o['p'])
            lo, hi = bisect.bisect_left(ds, d0 - 3), bisect.bisect_right(ds, d0 + 3)
            w = [e for _, e in nums[lo:hi]]
            if len(w) >= 3:
                o['e'] = int(statistics.median(w))
                o['x'] = 1
    # quality: smoothed like ratio, then percentile within upload year
    r = [o['l'] / o['v'] for o in data if o['l'] > 0 and o['v'] > 5000]
    prior = statistics.median(r) if r else 0.01
    M = 3000
    for o in data:
        l, v = o['l'], o['v']
        if l == 0 and v > 1000:
            l = prior * v
        o['q'] = round(1000 * (l + M * prior) / (v + M), 1)
    by = collections.defaultdict(list)
    for o in data:
        by[o['p'][:4]].append(o)
    for g in by.values():
        qs, vs = sorted(o['q'] for o in g), sorted(o['v'] for o in g)
        for o in g:
            o['z'] = round(0.6 * bisect.bisect_left(qs, o['q']) / len(g) + 0.4 * bisect.bisect_left(vs, o['v']) / len(g), 3)
    # merge duplicate uploads of the same (really numbered) episode
    groups = collections.defaultdict(list)
    for o in data:
        if o['k'] == 'episode' and o['e'] and not o['x']:
            groups[o['e']].append(o)
    drop = set()
    for g in groups.values():
        if len(g) > 1:
            g.sort(key=lambda o: (-(900 <= o['s'] <= 2700), -o['v']))
            g[0]['o'] = [[a['id'], a['p'], a['s'], a['v']] for a in g[1:]]
            g[0]['d'] = max((a['d'] for a in g), key=len)   # keep the fullest story text for search
            drop |= {a['id'] for a in g[1:]}
    out = []
    for o in data:
        if o['id'] in drop:
            continue
        o.pop('l', None)
        out.append(o)
    return {'data': out, 'chars': CHN, 'themes': THN}


def render(bundle, template_path, out_path):
    t = open(template_path, encoding='utf-8').read()
    marker = '/*DATA*/{data:[],chars:[],themes:[]}'
    assert marker in t
    js = json.dumps(bundle, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    open(out_path, 'w', encoding='utf-8').write(t.replace(marker, js))
