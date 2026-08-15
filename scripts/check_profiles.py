import tomllib

for city in ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']:
    with open(f'data/cities/{city}.toml', 'rb') as fh:
        d = tomllib.load(fh)
    rw = d['religion_weights']
    pumas = d['pumas']
    nb = len(d.get('neighborhoods', []))
    cz = len(d.get('centroids', []))
    pol = d.get('politics', {})
    vf = len(pol.get('vote_facts', ''))
    print(f"{city}: religion_weights len={len(rw)} sum={sum(rw):.3f} pumas={len(pumas)} "
          f"neighborhoods={nb} centroids={cz} vote_facts_len={vf}")
