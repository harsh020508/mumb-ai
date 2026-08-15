#!/usr/bin/env python3
"""
Generate synthetic PUMS-like data for Mumbai matching Census 2011 targets.
"""

import csv
import numpy as np

np.random.seed(42)

# Census 2011 targets for Greater Mumbai UA
TARGETS = {
    'population': 18_414_288,
    'sex_ratio_female_per_1000_male': 853,  # 46.0% female
    'median_age': 29,
    'literacy_rate': 0.8973,
    'workforce_participation': 0.395,
    'religion': {
        'hindu': 0.6599,
        'muslim': 0.2065,
        'buddhist': 0.0485,
        'jain': 0.0410,
        'christian': 0.0327,
        'other': 0.0114,
    },
    'sc_st': {'sc': 0.0713, 'st': 0.0081},
    'migration_inter_state': 0.35,
}

N_RECORDS = 10000

# PWGTP weight so sum matches target population
pwgtp_per_record = TARGETS['population'] / N_RECORDS

# Age distribution based on Census 2011 Mumbai (approximate)
# Using a piecewise distribution matching Indian age pyramid
def generate_ages(n):
    # Age groups with proportions for Mumbai
    # 0-14: ~25%, 15-29: ~28%, 30-44: ~25%, 45-59: ~15%, 60+: ~7%
    bins = [(0, 14), (15, 29), (30, 44), (45, 59), (60, 100)]
    probs = [0.25, 0.28, 0.25, 0.15, 0.07]
    ages = []
    for _ in range(n):
        bin_idx = np.random.choice(len(bins), p=probs)
        low, high = bins[bin_idx]
        ages.append(np.random.randint(low, high + 1))
    return np.array(ages)

# Sex: 1=Male, 2=Female, target 46% female
def generate_sex(n):
    return np.random.choice([1, 2], size=n, p=[0.54, 0.46])

# RAC1P encoding for Mumbai communities
# 1=Marathi Hindu, 2=North Indian Hindu, 3=Muslim, 4=Buddhist, 5=Jain, 6=Christian, 7=Sikh, 8=Other, 9=SC/ST
def generate_rac1p(n):
    probs = [0.35, 0.20, 0.20, 0.05, 0.04, 0.03, 0.01, 0.05, 0.07]
    return np.random.choice(range(1, 10), size=n, p=probs)

# Education (SCHL 1-24)
# Mumbai literacy 89.73% - encode as Census education levels
def generate_schl(n, ages):
    # Normalize probabilities so they always sum to 1.0
    p1 = [0.1, 0.1, 0.15, 0.15, 0.15, 0.15, 0.1, 0.05, 0.05]
    p2 = [0.05, 0.05, 0.1, 0.1, 0.15, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05]
    p3 = [0.05, 0.05, 0.08, 0.08, 0.1, 0.1, 0.1, 0.1, 0.08, 0.08, 0.05, 0.05, 0.03, 0.03, 0.01, 0.01]
    p3_mid = [0.1, 0.1, 0.1, 0.1, 0.15, 0.1, 0.1, 0.08, 0.05, 0.03, 0.03, 0.02, 0.01, 0.01, 0.01, 0.01]
    p3_el = [0.2, 0.15, 0.15, 0.15, 0.1, 0.1, 0.05, 0.1]
    
    # Ensure probabilities sum to 1
    def normalize(p):
        s = sum(p)
        return [x/s for x in p]
    
    p1 = normalize(p1)
    p2 = normalize(p2)
    p3 = normalize(p3)
    p3_mid = normalize(p3_mid)
    p3_el = normalize(p3_el)
    
    schl = []
    for age in ages:
        if age < 15:
            schl.append(np.random.choice([1, 2, 3, 4, 5, 6, 7, 8, 9], p=p1))
        elif age < 25:
            schl.append(np.random.choice([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], p=p2))
        elif age < 40:
            schl.append(np.random.choice([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], p=p3))
        elif age < 60:
            schl.append(np.random.choice([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], p=p3_mid))
        else:
            schl.append(np.random.choice([5, 6, 7, 8, 9, 10, 11, 12], p=p3_el))
    return np.array(schl)

# Income (PINCP) - Mumbai has high inequality, log-normal distribution
def generate_income(n, ages, schl):
    incomes = []
    for i in range(n):
        age = ages[i]
        edu = schl[i]
        # Base income by education and age
        if edu <= 8:  # Below secondary
            base = np.random.lognormal(9.5, 0.8)  # ~13,000 median
        elif edu <= 14:  # Secondary/HSC
            base = np.random.lognormal(10.5, 0.7)  # ~36,000 median
        elif edu <= 18:  # Graduate
            base = np.random.lognormal(11.5, 0.6)  # ~100,000 median
        else:  # Postgraduate+
            base = np.random.lognormal(12.2, 0.5)  # ~200,000 median
        
        # Age multiplier
        if age < 22:
            base *= 0.3
        elif age < 30:
            base *= 0.8
        elif age < 50:
            base *= 1.2
        elif age < 65:
            base *= 1.0
        else:
            base *= 0.5
        
        incomes.append(max(0, int(base)))
    return np.array(incomes)

# POVPIP: income-to-poverty ratio (0-501)
# Mumbai poverty line ~₹1000/person/month → ₹12,000/year
# POVPIP = income / poverty_line * 100
def generate_povpip(n, incomes):
    pov = []
    poverty_line = 12000  # annual per person
    for inc in incomes:
        ratio = inc / poverty_line * 100 if poverty_line > 0 else 501
        pov.append(min(501, max(0, int(ratio))))
    return np.array(pov)

# Occupation (OCCP) - Mumbai specific
def generate_occp(n, ages, schl):
    occs = []
    for i in range(n):
        age = ages[i]
        edu = schl[i]
        if age < 18 or age > 75:
            occs.append(0)  # Not in labor force
        elif edu <= 8:
            # Low education - informal, service, labor
            occs.append(np.random.choice([5000, 6000, 7000, 8000, 9000, 9800, 9920], p=[0.2, 0.15, 0.15, 0.1, 0.1, 0.15, 0.15]))
        elif edu <= 14:
            # Secondary - clerical, sales, skilled trades
            occs.append(np.random.choice([3000, 4000, 5000, 6000, 7000, 8000, 9000, 9800], p=[0.05, 0.05, 0.15, 0.2, 0.15, 0.1, 0.1, 0.2]))
        elif edu <= 18:
            # Graduate - professional, IT, finance, services
            occs.append(np.random.choice([1000, 2000, 3000, 4000, 5000, 6000], p=[0.1, 0.05, 0.2, 0.3, 0.15, 0.2]))
        else:
            # Postgrad - high-skill professional
            occs.append(np.random.choice([1000, 2000, 3000, 4000], p=[0.2, 0.1, 0.4, 0.3]))
    return np.array(occs)

# Class of Worker (COW)
def generate_cow(n, occp):
    cow = []
    for o in occp:
        if o == 0:
            cow.append(0)  # Not in labor force
        elif o in [1000, 2000, 3000, 4000]:
            cow.append(np.random.choice([1, 2, 3], p=[0.6, 0.2, 0.2]))  # Private, govt, self-emp
        else:
            cow.append(np.random.choice([1, 3, 4, 6], p=[0.5, 0.2, 0.2, 0.1]))  # Private, self-emp-inc, self-emp-not-inc, unemployed
    return np.array(cow)

# Employment Status (ESR)
def generate_esr(n, occp, ages):
    esr = []
    for i in range(n):
        o = occp[i]
        age = ages[i]
        if o == 0 or age < 16 or age > 75:
            esr.append(6)  # Not in labor force / under 16
        else:
            esr.append(np.random.choice([1, 2, 3, 4, 5], p=[0.75, 0.1, 0.05, 0.05, 0.05]))
    return np.array(esr)

# Citizenship (CIT)
def generate_cit(n):
    # Most born in India, some migrants from abroad, few foreign nationals
    return np.random.choice([1, 2, 5], size=n, p=[0.95, 0.03, 0.02])

# Marital Status (MAR)
def generate_mar(n, ages):
    mar = []
    for age in ages:
        if age < 18:
            mar.append(5)  # Never married
        elif age < 25:
            mar.append(np.random.choice([1, 5], p=[0.2, 0.8]))
        elif age < 35:
            mar.append(np.random.choice([1, 5], p=[0.7, 0.3]))
        elif age < 50:
            mar.append(np.random.choice([1, 2, 3, 5], p=[0.8, 0.05, 0.03, 0.12]))
        else:
            mar.append(np.random.choice([1, 2, 3, 4, 5], p=[0.65, 0.15, 0.05, 0.03, 0.12]))
    return np.array(mar)

# Nativity
def generate_nativity(n):
    return np.random.choice([1, 2], size=n, p=[0.95, 0.05])

# PUMA - Mumbai wards
def generate_puma(n):
    # 24 wards of Mumbai city, expanded
    wards = [2700100 + i for i in range(24)]
    return np.random.choice(wards, size=n)

def main():
    print(f"Generating {N_RECORDS} synthetic PUMS records for Mumbai...")
    
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
    output_path = 'data/mumbai_pums.csv'
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['SERIALNO', 'SPORDER', 'PWGTP', 'AGEP', 'SEX', 'RAC1P', 'HISP', 'SCHL', 'PINCP', 'POVPIP', 'OCCP', 'COW', 'ESR', 'CIT', 'MAR', 'NATIVITY', 'PUMA', 'ADJINC'])
        for i in range(N_RECORDS):
            serialno = f'2024MU{i+1:07d}'
            writer.writerow([
                serialno, 1, round(pwgtp_per_record, 2),
                ages[i], sex[i], rac1p[i], 1,  # HISP=1
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
    print(f"  Female %: {female_pct:.1f}% (target: 46.0%)")
    print(f"  Median age: {median_age:.1f} (target: ~29)")
    print(f"  Mean income: Rs {mean_income:,.0f}")
    print(f"  Total PWGTP sum: {N_RECORDS * pwgtp_per_record:,.0f} (target: {TARGETS['population']:,})")

if __name__ == '__main__':
    main()