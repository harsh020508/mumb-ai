import csv
import os

def load_stats(filepath):
    ages, sexes, incomes = [], {'M':0,'F':0}, []
    with open(filepath, 'r') as f:
        for row in csv.DictReader(f):
            try:
                ages.append(int(row['AGEP']))
            except:
                pass
            if row['SEX'] == '1': sexes['M'] += 1
            elif row['SEX'] == '2': sexes['F'] += 1
            try:
                incomes.append(float(row['PINCP']))
            except:
                pass
    n = len(ages)
    return {
        'n': n,
        'median_age': sorted(ages)[n//2] if n else 0,
        'female_pct': sexes['F']/(sexes['M']+sexes['F'])*100 if (sexes['M']+sexes['F']) else 0,
        'mean_income': sum(incomes)/len(incomes) if incomes else 0,
    }

sf = load_stats('data/sf_pums.csv')

def sim(a, b):
    if b == 0: return 100.0
    diff = abs(a-b)
    return max(0.0, (1 - diff/b) * 100)

cities = ['mumbai','delhi','kolkata','bangalore','jaipur']
print(f"{'City':<12}{'Age':>8}{'Sex':>8}{'Income':>10}{'Overall':>10}")
print('-' * 50)
total = 0
for city in cities:
    fp = f'data/{city}_pums.csv'
    if not os.path.exists(fp):
        print(f'{city}: MISSING FILE'); continue
    s = load_stats(fp)
    age_s = sim(s['median_age'], sf['median_age'])
    sex_s = sim(s['female_pct'], sf['female_pct'])
    inc_s = sim(s['mean_income'], sf['mean_income'])
    ov = (age_s + sex_s + inc_s) / 3
    total += ov
    print(f"{city:<12}{age_s:>7.1f}%{sex_s:>7.1f}%{inc_s:>9.1f}%{ov:>9.1f}%")

print(f"\nAverage accuracy across 5 cities: {total/5:.1f}%")
