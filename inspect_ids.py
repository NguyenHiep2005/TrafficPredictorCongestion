import json, glob, hashlib, collections

def make_segment_id(r):
    points = [(round(p['lat'], 5), round(p['lng'], 5))
              for link in r['location']['shape']['links']
              for p in link['points']]
    return hashlib.sha1(json.dumps(points).encode()).hexdigest()[:12]

files = sorted(glob.glob('data/samples/*.json'))
print('So file mau:', len(files))
ids_per_file = []
for f in files:
    d = json.load(open(f))
    ids = [make_segment_id(r) for r in d['results']]
    ids_per_file.append(set(ids))
    print(f, '| sourceUpdated:', d['sourceUpdated'], '| so doan:', len(ids), '| id duy nhat:', len(set(ids)))

d = json.load(open(files[0]))
cf = [r['currentFlow'] for r in d['results']]
print('currentFlow mau:', json.dumps(cf[0], indent=2))
ff = [c['freeFlow'] for c in cf if c.get('freeFlow') is not None]
jf = [c['jamFactor'] for c in cf if c.get('jamFactor') is not None]
print('freeFlow min/max:', min(ff), max(ff))
print('jamFactor min/max:', min(jf), max(jf))
print('confidence:', collections.Counter(c.get('confidence') for c in cf).most_common(5))
if len(files) > 1:
    print('So id co mat o moi file:', len(set.intersection(*ids_per_file)))
