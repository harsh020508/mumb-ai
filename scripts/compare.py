import csv

# Read SF data
with open('data/sf_pums.csv', 'r') as f:
    reader = csv.DictReader(f)
    sf_rows = list(reader)

# Read Mumbai data
with open('data/mumbai_pums.csv', 'r') as f:
    reader = csv.DictReader(f)
    mumbai_rows = list(reader)

print('=== SF Data Sample ===')
row = sf_rows[0]
print(f'AGEP={row["AGEP"]}, SEX={row["SEX"]}, RAC1P={row["RAC1P"]}, PINCP={row["PINCP"]}, PWGTP={row["PWGTP"]}')

print()
print('=== Mumbai Data Sample ===')
row = mumbai_rows[0]
print(f'AGEP={row["AGEP"]}, SEX={row["SEX"]}, RAC1P={row["RAC1P"]}, PINCP={row["PINCP"]}, PWGTP={row["PWGTP"]}')

# Compute distributions
sf_ages = [int(r['AGEP']) for r in sf_rows]
mumbai_ages = [int(r['AGEP']) for r in mumbai_rows]

print(f'\nSF age stats: min={min(sf_ages)}, max={max(sf_ages)}, median={sorted(sf_ages)[len(sf_ages)//2]}')
print(f'Mumbai age stats: min={min(mumbai_ages)}, max={max(mumbai_ages)}, median={sorted(mumbai_ages)[len(mumbai_ages)//2]}')

sf_sex = [r['SEX'] for r in sf_rows]
mumbai_sex = [r['SEX'] for r in mumbai_rows]
print(f'SF sex: M={sf_sex.count("1")}, F={sf_sex.count("2")} ({len(sf_rows)} records)')
print(f'Mumbai sex: M={mumbai_sex.count("1")}, F={mumbai_sex.count("2")} ({len(mumbai_rows)} records)')

sf_income = [float(r['PINCP']) for r in sf_rows if r['PINCP'].replace('.','',1).isdigit()]
mumbai_income = [float(r['PINCP']) for r in mumbai_rows if r['PINCP'].replace('.','',1).isdigit()]
print(f'SF income stats: mean={sum(sf_income)/len(sf_income):.1f}, median={sorted(sf_income)[len(sf_income)//2]:.1f}')
print(f'Mumbai income stats: mean={sum(mumbai_income)/len(mumbai_income):.1f}, median={sorted(mumbai_income)[len(mumbai_income)//2]:.1f}')