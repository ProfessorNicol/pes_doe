import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.graphics.factorplots import interaction_plot
import numpy as np
import json
import sys
import pdb
from copy import copy

if len(sys.argv) != 3:
    print(f"useage python plot.py arg_file data_file")
    exit(1)

try:
    with open(sys.argv[1],"r") as rf:
        data_factors = json.load(rf)
except Exception as e:
    print(f"Error Type {type(e).__name__}")
    print(f"Error Message {e}")
    exit(1)
    

factors = ('-arrival_rate', '-K', '-pS', '-pB', '-inv_mu1', '-inv_mu2')
factor_labels = ('lambda', 'K', 'pS', 'pB', '1.0/mu1', '1.0/mu2')

all_factors = list(data_factors)

for factor in all_factors:
    if not factor in factors:
        del data_factors[factor]

try:
    with open(sys.argv[2],"r") as rf:
        data_list = json.load(rf)
except Exception as e:
    print(f"error {e} with data file {sys.argv[2]}")

interaction_terms = ('-pB', '-inv_mu1')

def respMatch(msr, f1, f1_level, f2, f2_level):
    if msr[f1] != f1_level or msr[f2] != f2_level:
        return False
    return True

def responses(f1, f1_level, f2, f2_level, data_factors, data_list):
    f1_low  = data_factors[f1][0]
    f1_high = data_factors[f1][1]
    f2_low  = data_factors[f2][0]
    f2_high = data_factors[f2][1]

    if f1_level == 'low':
        f1_select = f1_low
    else:
        f1_select = f1_high

    if f2_level == 'low':
        f2_select = f2_low
    else:
        f2_select = f2_high

    num_sys = 0.0
    time_sys = 0.0
    util_sys = 0.0
    drop_pr = 0.0

    num_found = 0
    for msr in data_list:
        if respMatch(msr, f1, f1_select, f2, f2_select):
            num_found += 1
            num_sys  += msr["num_sys"]
            time_sys += msr["time_sys"]
            util_sys += msr["util_sys"]
            drop_pr  += msr["drop_pr"]

    return (num_sys/num_found, time_sys/num_found, util_sys/num_found, drop_pr/num_found)

response = {}

f1 = '-pS'
f2 = '-inv_mu1'
f1_name = 'pS'
f2_name = '1.0/mu1'

{('f1Low','f2Low'):[], \
    ('f1Low', 'f2High'): [], \
    ('f1High', 'f2Low'): [], \
    ('f1High', 'f2High'):[]}

response[('f1Low','f2Low')]  = responses(f1, 'low', f2, 'low', data_factors, data_list)
response[('f1Low','f2High')] = responses(f1, 'low', f2, 'high', data_factors, data_list)
response[('f1High','f2Low')] = responses(f1, 'high', f2, 'low', data_factors, data_list)
response[('f1High','f2High')] = responses(f1, 'high', f2, 'high', data_factors, data_list)

measures = ('E[N]', 'E[W]', 'util', 'Pr{drop}')
measure_code = ('N', 'W','rho','pr')

sys_avg = [0.0]*4
for key, resp in response.items():
    for i in range(0,4):
        sys_avg[i] += resp[i]

for i in range(0,4):
    sys_avg[i] /= 4


for midx, measure in enumerate(measures):
    values = [0]*4
    values[0] = response[('f1Low','f2Low')][midx]
    values[1] = response[('f1Low','f2High')][midx]
    values[2] = response[('f1High','f2Low')][midx]
    values[3] = response[('f1High','f2High')][midx]
    # Create dataframe
    data = pd.DataFrame(
        {
            f1_name: ["low", "low", "high", "high"],
            f2_name: ["low", "high", "low", "high"],
            "Response": values,
        }
    )

    # Generate interaction plot
    fig, ax = plt.subplots(figsize=(8,5))
    fig = interaction_plot(
        x=data[f1_name],
        trace=data[f2_name],
        response=data["Response"],
        colors=["blue", "red"],
        markers=["o", "^"], ax=ax
    )

    mean_value = sys_avg[midx]
    ax.axhline(y=mean_value, color='black', linestyle='--', linewidth=2, label=f'Mean: {mean_value:.2f}')

    plt.ylabel(f"{measures[midx]}")
    plt.title("Interaction Plot for pS and 1.0/mu1")
    fname = f"interact-{measure_code[midx]}"
    plt.savefig(fname)

