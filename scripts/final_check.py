import csv
import statistics

targets = {
    'mumbai': {'female': 46.0, 'median_age': 29, 'pop': 18414288},
    'delhi': {'female': 46.7, 'median_age': 28, 'pop': 16787941},
    'kolkata': {'female': 47.6, 'median_age': 31, 'pop': 4496694},
    'bangalore': {'female': 48.0, 'median_age': 27, 'pop': 8443675},
    'jaipur': {'female': 47.6, 'median_age': 26, 'pop': 3046163},
}

print(f"{'city':<10}{'rows':>7}{'female%':>9}{'tgt':>6}{'med_age':>8}{'tgt':>5}{'PWGTP':>12}")
for city, t in targets.items():
    rows = list(csv.DictReader(open(f'data/{city}_pums.csv')))
    ages = [int(r['AGEP']) for r in rows]
    sexes = [r['SEX'] for r in rows]
    female = sexes.count('2') / len(sexes) * 100
    med = statistics.median(ages)
    pwgt = sum(float(r['PWGTP']) for r in rows)
    print(f"{city:<10}{len(rows):>7}{female:>8.1f}%{t['female']:>6.1f}"
          f"{med:>8.1f}{t['median_age']:>5.1f}{pwgt/1e6:>10.1f}M")
    assert len(rows) == 10000, f'{city} rows != 10000'
print("\nAll cities: 10,000 rows each — PASS")