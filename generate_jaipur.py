import csv
import random

# Headers: SERIALNO,SPORDER,PWGTP,AGEP,SEX,RAC1P,HISP,SCHL,PINCP,POVPIP,OCCP,COW,ESR,CIT,MAR,NATIVITY,PUMA,ADJINC

with open('data/jaipur_pums.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['SERIALNO','SPORDER','PWGTP','AGEP','SEX','RAC1P','HISP','SCHL','PINCP','POVPIP','OCCP','COW','ESR','CIT','MAR','NATIVITY','PUMA','ADJINC'])
    for i in range(1, 1001):
        serial = f"2023GQ{i:06d}"
        sporder = 1
        pwgtp = random.randint(10, 200)
        age = random.randint(18, 90)
        sex = random.choice([1, 2])
        rac1p = random.choice([1, 2, 6, 8, 9])
        hisp = random.choice([1, 2, 3])
        schl = random.randint(1, 24)
        pincp = random.randint(0, 150000)
        povpip = random.randint(0, 501)
        occp = random.randint(0, 9920)
        cow = random.randint(0, 9)
        esr = random.choice([1, 2, 3, 4, 5, 6])
        cit = random.choice([1, 2, 3, 4, 5])
        mar = random.choice([1, 2, 3, 4, 5])
        nativity = random.choice([1, 2])
        puma = "08101" # dummy puma for jaipur
        adjinc = 1019518
        writer.writerow([serial, sporder, pwgtp, age, sex, rac1p, hisp, schl, pincp, povpip, occp, cow, esr, cit, mar, nativity, puma, adjinc])
