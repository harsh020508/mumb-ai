#!/usr/bin/env python3
import csv

def validate_csv(filepath):
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f'File: {filepath}')
    print(f'  Rows: {len(rows)}')
    print(f'  Columns: {len(reader.fieldnames)}')
    
    required = ['SERIALNO', 'SPORDER', 'PWGTP', 'AGEP', 'SEX', 'RAC1P', 'HISP', 'SCHL', 'PINCP', 'POVPIP', 'OCCP', 'COW', 'ESR', 'CIT', 'MAR', 'NATIVITY', 'PUMA', 'ADJINC']
    missing = [f for f in required if f not in reader.fieldnames]
    if missing:
        print(f'  MISSING FIELDS: {missing}')
    else:
        print(f'  All required fields present')
    
    ages = [int(r['AGEP']) for r in rows if r['AGEP'].isdigit()]
    pwgtps = [float(r['PWGTP']) for r in rows if r['PWGTP']]
    sexes = [r['SEX'] for r in rows]
    
    male_count = sexes.count('1')
    female_count = sexes.count('2')
    
    print(f'  Age range: {min(ages)}-{max(ages)}, median: {sorted(ages)[len(ages)//2]}')
    print(f'  PWGTP range: {min(pwgtps):.1f}-{max(pwgtps):.1f}, sum: {sum(pwgtps):.0f}')
    print(f'  Sex distribution: M={male_count}, F={female_count}')
    print()

files = [
    'data/mumbai_pums.csv',
    'data/delhi_pums.csv',
    'data/kolkata_pums.csv',
    'data/bangalore_pums.csv',
    'data/jaipur_pums.csv'
]

for f in files:
    try:
        validate_csv(f)
    except Exception as e:
        print(f'Error reading {f}: {e}')
        print()