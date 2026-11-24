import json, glob, sys

path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob('data/samples/*.json'))[0]
d = json.load(open(path))

print('Cac khoa cap cao:', list(d.keys()))
print('So doan duong:', len(d['results']))
print(json.dumps(d['results'][0], indent=2)[:1500])

speeds = [x['currentFlow']['speed'] for x in d['results']]
print('speed min/max:', min(speeds), max(speeds))
