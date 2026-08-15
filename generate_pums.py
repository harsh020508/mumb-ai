import csv
import random

# PUMS structure:
# SERIALNO,SPORDER,PWGTP,AGEP,SEX,RAC1P,HISP,SCHL,PINCP,POVPIP,OCCP,COW,ESR,CIT,MAR,NATIVITY,PUMA,ADJINC
# Let's generate 1000 records.
fieldnames = ['SERIALNO', 'SPORDER', 'PWGTP', 'AGEP', 'SEX', 'RAC1P', 'HISP', 'SCHL', 'PINCP', 'POVPIP', 'OCCP', 'COW', 'ESR', 'CIT', 'MAR', 'NATIVITY', 'PUMA', 'ADJINC']

rows = []
for i in range(1000):
    row = {
        'SERIALNO': f'2023KOL{i:05}',
        'SPORDER': 1,
        'PWGTP': random.randint(1, 100),
        'AGEP': random.randint(18, 90),
        'SEX': random.choice([1, 2]),
        'RAC1P': random.choice([1, 2, 3, 4, 5, 6, 7, 8]),
        'HISP': random.choice([1, 2]),
        'SCHL': random.randint(1, 24),
        'PINCP': random.randint(0, 100000),
        'POVPIP': random.randint(0, 500),
        'OCCP': random.choice([0, 1000, 2000, 3000, 4000]),
        'COW': random.choice([0, 1, 2, 3, 4, 5]),
        'ESR': random.choice([1, 2, 3, 6]),
        'CIT': random.choice([1, 2, 3, 4, 5]),
        'MAR': random.choice([1, 2, 3, 4, 5]),
        'NATIVITY': random.choice([1, 2]),
        'PUMA': random.choice([101, 102, 103, 104, 105]),
        'ADJINC': 1000000 
    }
    rows.append(row)

with open('data/kolkata_pums.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
