#!/usr/bin/env python3
"""
Generate synthetic PUMS-like data for Bangalore matching Census 2011 targets.
"""

import csv
import numpy as np

np.random.seed(45)

# Census 2011 targets for Bangalore (BBMP)
TARGETS = {
    'population': 8_443_675,
    'sex_ratio_female_per_1000_male': 923,  # ~48.0% female
    'median_age': 27,
    'literacy_rate': 0.8871,
    'workforce_participation': 0.425,
}

N_RECORDS = 10000
pwgtp_per_record = TARGETS['population'] / N_RECORDS

def generate_ages(n):
    bins = [(0, 14), (15, 29), (30, 44), (45, 59), (60, 100)]
    probs = [0.22, 0.33, 0.28, 0.12, 0.05]
    ages = []
    for _ in range(n):
        bin_idx = np.random.choice(len(bins), p=probs)
        low, high = bins[bin_idx]
        ages.append(np.random.randint(low, high + 1))
    return np.array(ages)

def generate_sex(n):
    return np.random.choice([1, 2], size=n, p=[0.52, 0.48])

# 1=Kannada Hindu, 2=Tamil migrant, 3=Telugu migrant, 4=Kerala, 5=North Indian, 6=Muslim, 7=Christian, 8=Anglo-Indian, 9=Other
def generate_rac1p(n):
    probs = [0.42, 0.15, 0.12, 0.06, 0.10, 0.10, 0.03, 0.01, 0.01]
    return np.random.choice(range(1, 10), size=n, p=probs)

def _norm(p):
    s = sum(p)
    return [x/s for x in p] if s > 0 else p

def generate_schl(n, ages):
    p_child = _norm([0.1, 0.1, 0.15, 0.16, 0.15, 0.13, 0.1, 0.06, 0.05])
    p_youth = _norm([0.03, 0.04, 0.07, 0.09, 0.12, 0.1, 0.12, 0.15, 0.15, 0.08, 0.05])
    p_work = _norm([0.04, 0.04, 0.06, 0.07, 0.08, 0.08, 0.1, 0.1, 0.1, 0.1, 0.08, 0.06, 0.03, 0.02, 0.01])
    p_mid = _norm([0.07, 0.07, 0.09, 0.1, 0.11, 0.1, 0.1, 0.09, 0.07, 0.06, 0.04, 0.02, 0.02, 0.01])
    p_old = _norm([0.2, 0.19, 0.16, 0.13, 0.1, 0.09, 0.07, 0.06])
    schl = []
    for age in ages:
        if age < 15:
            schl.append(np.random.choice([1, 2, 3, 4, 5, 6, 7, 8, 9], p=p_child))
        elif age < 25:
            schl.append(np.random.choice([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], p=p_youth))
        elif age < 45:
            schl.append(np.random.choice([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], p=p_work))
        elif age < 60:
            schl.append(np.random.choice([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18], p=p_mid))
        else:
            schl.append(np.random.choice([5, 6, 7, 8, 9, 10, 11, 12], p=p_old))
    return np.array(schl)

def generate_income(n, ages, schl):
    incomes = []
    for i in range(n):
        age = ages[i]
        edu = schl[i]
        if edu <= 8:
            base = np.random.lognormal(9.6, 0.7)
        elif edu <= 14:
            base = np.random.lognormal(10.6, 0.6)
        elif edu <= 18:
            base = np.random.lognormal(11.6, 0.5)
        else:
            base = np.random.lognormal(12.3, 0.5)
        if age < 22:
            base *= 0.4
        elif age < 30:
            base *= 0.8
        elif age < 50:
            base *= 1.15
        elif age < 65:
            base *= 1.0
        else:
            base *= 0.6
        incomes.append(max(0, int(base)))
    return np.array(incomes)

def generate_povpip(n, incomes):
    pov = []
    poverty_line = 14000
    for inc in incomes:
        ratio = inc / poverty_line * 100 if poverty_line > 0 else 501
        pov.append(min(501, max(0, int(ratio))))
    return np.array(pov)

def generate_occp(n, ages, schl):
    occs = []
    for i in range(n):
        age = ages[i]
        edu = schl[i]
        if age < 18 or age > 70:
            occs.append(0)
        elif edu <= 8:
            occs.append(np.random.choice([5000, 6000, 7000, 8000, 9000, 9800, 9920], p=[0.2, 0.15, 0.15, 0.1, 0.1, 0.15, 0.15]))
        elif edu <= 14:
            occs.append(np.random.choice([1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 9800], p=[0.06, 0.04, 0.06, 0.2, 0.16, 0.18, 0.1, 0.08, 0.08, 0.04]))
        elif edu <= 18:
            occs.append(np.random.choice([1000, 2000, 3000, 4000, 5000, 6000], p=[0.1, 0.06, 0.12, 0.45, 0.12, 0.15]))
        else:
            occs.append(np.random.choice([1000, 2000, 3000, 4000], p=[0.18, 0.1, 0.15, 0.57]))
    return np.array(occs)

def generate_cow(n, occp):
    cow = []
    for o in occp:
        if o == 0:
            cow.append(0)
        elif o in [1000, 2000, 3000, 4000]:
            cow.append(np.random.choice([1, 2, 3], p=[0.7, 0.15, 0.15]))
        else:
            cow.append(np.random.choice([1, 3, 4, 6], p=[0.55, 0.2, 0.15, 0.1]))
    return np.array(cow)

def generate_esr(n, occp, ages):
    esr = []
    for i in range(n):
        o = occp[i]
        age = ages[i]
        if o == 0 or age < 16 or age > 70:
            esr.append(6)
        else:
            esr.append(np.random.choice([1, 2, 3, 4, 5], p=[0.85, 0.05, 0.03, 0.03, 0.04]))
    return np.array(esr)

def generate_cit(n):
    return np.random.choice([1, 2, 5], size=n, p=[0.98, 0.01, 0.01])

def generate_mar(n, ages):
    mar = []
    for age in ages:
        if age < 18:
            mar.append(5)
        elif age < 25:
            mar.append(np.random.choice([1, 5], p=[0.2, 0.8]))
        elif age < 35:
            mar.append(np.random.choice([1, 5], p=[0.65, 0.35]))
        elif age < 50:
            mar.append(np.random.choice([1, 2, 3, 5], p=[0.8, 0.04, 0.02, 0.14]))
        else:
            mar.append(np.random.choice([1, 2, 3, 4, 5], p=[0.68, 0.14, 0.04, 0.02, 0.12]))
    return np.array(mar)

def generate_nativity(n):
    return np.random.choice([1, 2], size=n, p=[0.97, 0.03])

def generate_puma(n):
    zones = [2900100 + i for i in range(8)]
    return np.random.choice(zones, size=n)

def main():
    print(f"Generating {N_RECORDS} synthetic PUMS records for Bangalore...")
    ages = generate_ages(N_RECORDS)
    sex = generate_sex(N_RECORDS)
    rac1p = generate_rac1p(N_RECORDS)
    schl = generate_schl(N_RECORDS, ages)
    pincp = generate_income(N_RECORDS, ages, schl)
    povpip = generate_povpip(N_RECORDS, pincp)
    occp = generate_occp(N_RECORDS, ages, schl)
    cow = generate_cow(N_RECORDS, occp)
    esr = generate_esr(N_RECORDS, occp, ages)
    cit = generate_cit(N_RECORDS)
    mar = generate_mar(N_RECORDS, ages)
    nativity = generate_nativity(N_RECORDS)
    puma = generate_puma(N_RECORDS)

    output_path = 'data/bangalore_pums.csv'
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['SERIALNO', 'SPORDER', 'PWGTP', 'AGEP', 'SEX', 'RAC1P', 'HISP', 'SCHL', 'PINCP', 'POVPIP', 'OCCP', 'COW', 'ESR', 'CIT', 'MAR', 'NATIVITY', 'PUMA', 'ADJINC'])
        for i in range(N_RECORDS):
            writer.writerow([
                f'2024BG{i+1:07d}', 1, round(pwgtp_per_record, 2),
                ages[i], sex[i], rac1p[i], 1,
                schl[i], pincp[i], povpip[i],
                occp[i], cow[i], esr[i], cit[i],
                mar[i], nativity[i], puma[i], 1000000
            ])

    print(f"Written to {output_path}")
    female_pct = (sex == 2).mean() * 100
    print(f"Validation: Female % = {female_pct:.1f} (target 48.0), Median age = {np.median(ages):.1f} (target ~27), Rows = {N_RECORDS}")

if __name__ == '__main__':
    main()