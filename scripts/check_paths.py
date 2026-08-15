import glob
import os
import re

for f in glob.glob('config/cities/*.toml'):
    t = open(f).read()
    for m in re.finditer(r'"([^"]+)"', t):
        p = m.group(1)
        if not p.startswith('data/') and not p.startswith('assets/'):
            continue
        status = 'EXISTS' if os.path.exists(p) else 'MISSING'
        print(f'{f:40} {p:40} {status}')
