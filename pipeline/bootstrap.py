"""One-time: turn the raw catalog fetched earlier into data/videos.json."""
import collections, json, sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import lib

raw = json.load(open(sys.argv[1]))                 # catalog.json (raw videos)
members = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}   # id -> playlist titles
pcount = collections.Counter(p for v in members.values() for p in set(v))
out = []
for r in raw:
    rec = lib.ingest(r, [p for p in members.get(r['id'], []) if pcount[p] < 200])
    if rec:
        out.append(rec)
out.sort(key=lambda o: (o['p'], o['id']))
json.dump(out, open('data/videos.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(len(out), 'site videos')
