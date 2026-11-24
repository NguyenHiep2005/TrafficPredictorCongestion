import json, glob, hashlib

def sid(r):
    pts = [(round(p['lat'], 5), round(p['lng'], 5))
           for l in r['location']['shape']['links'] for p in l['points']]
    return hashlib.sha1(json.dumps(pts).encode()).hexdigest()[:12]

data = []
for f in glob.glob('data/samples/*.json'):
    d = json.load(open(f))
    data.append((d['sourceUpdated'], {sid(r): r['currentFlow'] for r in d['results']}))
data.sort(key=lambda x: x[0])

for (t1, a), (t2, b) in zip(data, data[1:]):
    common = set(a) & set(b)
    changed = sum(1 for k in common if a[k]['speed'] != b[k]['speed'])
    print(t1, '->', t2, '| doan doi toc do:', changed, '/', len(common))
