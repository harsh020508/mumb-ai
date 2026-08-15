import tomllib

for city in ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']:
    with open(f'data/cities/{city}.toml', 'rb') as f:
        d = tomllib.load(f)
    rw = d['religion_weights']
    assert abs(sum(rw) - 1.0) < 0.01, f'{city} religion_weights sum != 1'
    assert len(rw) == 9, f'{city} expected 9 religion weights, got {len(rw)}'
    pumas = d['pumas']
    nb = len(d.get('neighborhoods', []))
    cz = len(d.get('centroids', []))
    print(f'{city}: OK - religion_weights len={len(rw)} sum={sum(rw):.3f} pumas={len(pumas)} nb={nb} centroids={cz}')

# Check news files
import json, os
for city in ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur', 'sf', 'neu_york', 'simami', 'cybercago', 'synth_la']:
    path = f'data/news/{city}.json'
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        print(f'{city}: news OK - {len(data)} articles')
    else:
        print(f'{city}: news MISSING')

print('\nAll profiles valid!')