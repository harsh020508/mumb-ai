#!/usr/bin/env python3
"""
Generate synthetic PUMS-like data for Delhi matching Census 2011 targets.
"""

import csv
import numpy as np

np.random.seed(43)  # Different seed for Delhi

# Census 2011 targets for Delhi NCT
TARGETS = {
    'population': 16_787_941,
    'sex_ratio_female_per_1000_male': 868,  # 46.7% female
    'median_age': 28,
    'literacy_rate': 0.8621,
    'workforce_participation': 0.333,
    'religion': {
        'hindu': 0.8168,
        'muslim': 0.1286,
        'sikh': 0.0340,
        'christian': 0.0087,
        'other': 0.0119,  # remainder
    },
    'sc_st': {'sc': 0.1675, 'st': 0.0066},
    'migration_inter_state': 0.45,
}

N_RECORDS = 10000

# PWGTP weight so sum matches target population
pwgtp_per_record = TARGETS['population'] / N_RECORDS

# Age distribution for Delhi (similar to Mumbai but slightly younger due to high migrant workforce)
def generate_ages(n):
    # Delhi: 0-14 ~26%, 15-29 ~30%, 30-44 ~24%, 45-59 ~14%, 60+ ~6%
    bins = [(0, 14), (15, 29), (30, 44), (45, 59), (60, 100)]
    probs = [0.26, 0.30, 0.24, 0.14, 0.06]
    ages = []
    for _ in range(n):
        bin_idx = np.random.choice(len(bins), p=probs)
        low, high = bins[bin_idx]
        ages.append(np.random.randint(low, high + 1))
    return np.array(ages)

# Sex: 1=Male, 2=Female, target 46.7% female
def generate_sex(n):
    return np.random.choice([1, 2], size=n, p=[0.533, 0.467])

# RAC1P encoding for Delhi communities
# 1=Hindi belt Hindu (UP/Bihar/Haryana), 2=Punjabi Hindu/Sikh, 3=Muslim, 4=Baniya/trader, 5=SC/Dalit, 6=OBC, 7=Christian, 8=Sikh, 9=Other
def generate_rac1p(n):
    probs = [0.35, 0.15, 0.13, 0.10, 0.12, 0.10, 0.01, 0.02, 0.02]
    return np.random.choice(range(1, 10), size=n, p=probs)

# Education (SCHL 1-24)
def generate_schl(n, ages):
    # Normalize probabilities helper
    def normalize(p):
        s = sum(p)
        return [x/s for x in p] if s>0 else p
    
    # Children
    p_child = normalize([0.12, 0.12, 0.16, 0.16, 0.14, 0.12, 0.08, 0.05, 0.05])
    # Youth (15-24)
    p_youth = normalize([0.05, 0.05, 0.1, 0.1, 0.15, 0.1, 0.1, 0.1, 0.1, 0.08, 0.07])
    # Working age (25-44) - 16 categories (5-20)
    p_work = normalize([0.06, 0.06, 0.08, 0.08, 0.1, 0.1, 0.1, 0.1, 0.09, 0.09, 0.06, 0.04, 0.02, 0.02, 0.01, 0.01])
    # Middle age (45-59) - 16 categories (5-20)
    p_mid = normalize([0.08, 0.08, 0.1, 0.1, 0.12, 0.1, 0.1, 0.08, 0.06, 0.04, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01])
    # Elderly (60+) - 8 categories (5-12)
    p_old = normalize([0.25, 0.2, 0.15, 0.1, 0.1, 0.08, 0.07, 0.05])
    
    schl = []
    for age in ages:
        if age < 15:
            schl.append(np.random.choice([1,2,3,4,5,6,7,8,9], p=p_child))
        elif age < 25:
            schl.append(np.random.choice([10,11,12,13,14,15,16,17,18,19,20], p=p_youth))
        elif age < 45:
            schl.append(np.random.choice([5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20], p=p_work))
        elif age < 60:
            schl.append(np.random.choice([5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20], p=p_mid))
        else:
            schl.append(np.random.choice([5,6,7,8,9,10,11,12], p=p_old))
    return np.array(schl)

# Income (PINCP) - Delhi has high incomes but inequality
def generate_income(n, ages, schl):
    incomes = []
    for i in range(n):
        age = ages[i]
        edu = schl[i]
        if edu <= 8:
            base = np.random.lognormal(9.8, 0.7)   # ~18,000 median
        elif edu <= 14:
            base = np.random.lognormal(10.6, 0.6)  # ~40,000 median
        elif edu <= 18:
            base = np.random.lognormal(11.4, 0.5)  # ~90,000 median
        else:
            base = np.random.lognormal(12.0, 0.5)  # ~160,000 median
        
        if age < 22:
            base *= 0.4
        elif age < 30:
            base *= 0.8
        elif age < 50:
            base *= 1.1
        elif age < 65:
            base *= 1.0
        else:
            base *= 0.6
        
        incomes.append(max(0, int(base)))
    return np.array(incomes)

# POVPIP: income-to-poverty ratio (Delhi poverty line higher)
def generate_povpip(n, incomes):
    pov = []
    poverty_line = 15000  # annual per person, higher than Mumbai
    for inc in incomes:
        ratio = inc / poverty_line * 100 if poverty_line > 0 else 501
        pov.append(min(501, max(0, int(ratio))))
    return np.array(pov)

# Occupation (OCCP) - Delhi specific: government high
def generate_occp(n, ages, schl):
    occs = []
    for i in range(n):
        age = ages[i]
        edu = schl[i]
        if age < 18 or age > 70:
            occs.append(0)
        elif edu <= 8:
            occs.append(np.random.choice([5000, 6000, 7000, 8000, 9000, 9800, 9920], p=[0.2,0.15,0.15,0.1,0.1,0.15,0.15]))
        elif edu <= 14:
            occs.append(np.random.choice([1000,2000,3000,4000,5000,6000,7000,8000,9000,9800], p=[0.08,0.05,0.05,0.05,0.15,0.2,0.15,0.1,0.12,0.05]))
        elif edu <= 18:
            occs.append(np.random.choice([1000,2000,3000,4000,5000,6000], p=[0.15,0.1,0.15,0.3,0.15,0.15]))
        else:
            occs.append(np.random.choice([1000,2000,3000,4000], p=[0.2,0.1,0.4,0.3]))
    return np.array(occs)

# Class of Worker (COW)
def generate_cow(n, occp):
    cow = []
    for o in occp:
        if o == 0:
            cow.append(0)
        elif o in [1000,2000,3000,4000]:
            cow.append(np.random.choice([1,2,3], p=[0.55,0.25,0.2]))  # Delhi has higher govt share
        else:
            cow.append(np.random.choice([1,3,4,6], p=[0.5,0.2,0.2,0.1]))
    return np.array(cow)

# Employment Status (ESR)
def generate_esr(n, occp, ages):
    esr = []
    for i in range(n):
        o = occp[i]
        age = ages[i]
        if o == 0 or age < 16 or age > 70:
            esr.append(6)
        else:
            esr.append(np.random.choice([1,2,3,4,5], p=[0.78,0.08,0.04,0.04,0.06]))
    return np.array(esr)

# Citizenship (CIT)
def generate_cit(n):
    return np.random.choice([1,2,5], size=n, p=[0.92,0.06,0.02])  # Delhi more migrants

# Marital Status (MAR)
def generate_mar(n, ages):
    mar = []
    for age in ages:
        if age < 20:
            mar.append(5)
        elif age < 25:
            mar.append(np.random.choice([1,5], p=[0.25,0.75]))
        elif age < 35:
            mar.append(np.random.choice([1,5], p=[0.6,0.4]))
        elif age < 50:
            mar.append(np.random.choice([1,2,3,5], p=[0.78,0.05,0.03,0.14]))
        else:
            mar.append(np.random.choice([1,2,3,4,5], p=[0.62,0.18,0.05,0.03,0.12]))
    return np.array(mar)

# Nativity
def generate_nativity(n):
    return np.random.choice([1,2], size=n, p=[0.88,0.12])  # Delhi high in-migration

# PUMA - Delhi districts (11 districts, using 6-digit base)
def generate_puma(n):
    districts = [700700 + i for i in range(11)]  # 0700700 to 0700710
    return np.random.choice(districts, size=n)

def main():
    print(f"Generating {N_RECORDS} synthetic PUMS records for Delhi...")
    
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
    
    # Write CSV
    output_path = 'data/delhi_pums.csv'
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['SERIALNO', 'SPORDER', 'PWGTP', 'AGEP', 'SEX', 'RAC1P', 'HISP', 'SCHL', 'PINCP', 'POVPIP', 'OCCP', 'COW', 'ESR', 'CIT', 'MAR', 'NATIVITY', 'PUMA', 'ADJINC'])
        for i in range(N_RECORDS):
            serialno = f'2024DL{i+1:07d}'
            writer.writerow([
                serialno, 1, round(pwgtp_per_record, 2),
                ages[i], sex[i], rac1p[i], 1,
                schl[i], pincp[i], povpip[i],
                occp[i], cow[i], esr[i], cit[i],
                mar[i], nativity[i], puma[i], 1000000
            ])
    
    print(f"Written to {output_path}")
    
    # Quick validation
    female_pct = (sex == 2).mean() * 100
    median_age = np.median(ages)
    mean_income = pincp.mean()
    print(f"\nValidation vs Census targets:")
    print(f"  Female %: {female_pct:.1f}% (target: 46.7%)")
    print(f"  Median age: {median_age:.1f} (target: ~28)")
    print(f"  Mean income: ₹{mean_income:,.0f}")
    print(f"  Total PWGTP sum: {N_RECORDS * pwgtp_per_record:,.0f} (target: {TARGETS['population']:,})")

if __name__ == '__main__':
    main()