"""One-off: which channels dominate Gujarati devotional / lagna geet searches?  Writes data/probe_mummy.json"""
import json, os, urllib.parse, urllib.request, urllib.error, collections
KEY = os.environ['YT_KEY']
QUERIES = ['gujarati bhajan', 'gujarati prabhatiya', 'gujarati aarti', 'gujarati lagna geet', 'lagna geet gujarati wedding songs',
           'gujarati santvani', 'gujarati hanuman chalisa', 'gujarati shiv bhajan', 'swaminarayan kirtan gujarati',
           'gujarati krishna bhajan', 'gujarati garba nonstop', 'gujarati dhun kirtan', 'gujarati katha satsang']

def api(ep, **p):
    p['key'] = KEY
    try:
        with urllib.request.urlopen('https://www.googleapis.com/youtube/v3/%s?%s' % (ep, urllib.parse.urlencode(p)), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'items': []}

out = {'queries': {}, 'channels': {}}
chan = collections.Counter(); names = {}
for q in QUERIES:
    d = api('search', part='snippet', q=q, type='video', videoEmbeddable='true', order='viewCount', maxResults=25, regionCode='IN', relevanceLanguage='gu')
    rows = [(i['snippet']['channelId'], i['snippet']['channelTitle'], i['snippet']['title'][:70]) for i in d.get('items', [])]
    out['queries'][q] = [{'ch': c[1], 't': c[2]} for c in rows[:8]]
    for c in rows:
        chan[c[0]] += 1; names[c[0]] = c[1]
top = chan.most_common(25)
ids = [c for c, _ in top]
for i in range(0, len(ids), 50):
    d = api('channels', part='snippet,statistics', id=','.join(ids[i:i+50]))
    for c in d.get('items', []):
        out['channels'][c['id']] = {'title': c['snippet']['title'], 'subs': c['statistics'].get('subscriberCount'),
                                    'videos': c['statistics'].get('videoCount'), 'hits': chan[c['id']], 'handle': c['snippet'].get('customUrl')}
json.dump(out, open('data/probe_mummy.json', 'w'), indent=1, ensure_ascii=False)
