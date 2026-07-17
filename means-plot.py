import matplotlib.pyplot as plt
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


x = []

# separate the records into those where match_factor is low, and those where match_factor is high,
# and compute the average conditioned on the separation.  Return low and high averages for all factors
#
def separate(match_factor, data_factors, data_list):
    num_sys_low_sum = 0.0
    num_sys_high_sum = 0.0
    time_sys_low_sum = 0.0
    time_high_sum = 0.0
    util_low_sum = 0.0
    util_high_sum = 0.0
    drop_pr_low_sum = 0.0
    drop_pr_high_sum = 0.0
 
    try: 
        low  = data_factors[match_factor][0]
        high = data_factors[match_factor][1]
    except:
        pdb.set_trace()
        x=1

    for msr in data_list:
        if msr[match_factor] == low:
            num_sys_low_sum  += msr["num_sys"]
            time_sys_low_sum += msr["time_sys"]
            util_low_sum += msr["util_sys"]
            drop_pr_low_sum  += msr["drop_pr"]
        elif msr[match_factor] == high:
            num_sys_high_sum  += msr["num_sys"]
            time_high_sum += msr["time_sys"]
            util_high_sum += msr["util_sys"]
            drop_pr_high_sum  += msr["drop_pr"]
        else:
            print(f"oops")
            exit(1)

    half = len(data_list)/2
    num_sys_low  = num_sys_low_sum/half
    num_sys_high = num_sys_high_sum/half
    time_sys_low  = time_sys_low_sum/half
    time_sys_high = time_high_sum/half
    util_sys_low  = util_low_sum/half
    util_sys_high = util_high_sum/half
    drop_pr_low  = drop_pr_low_sum/half
    drop_pr_high = drop_pr_high_sum/half

    return (num_sys_low, time_sys_low, util_sys_low, drop_pr_low, \
        num_sys_high, time_sys_high, util_sys_high, drop_pr_high) 

responses = ('E[N]', 'E[W]', 'util', 'Pr{drop}')
response_name = ['N', 'W', 'rho', 'prdrop']

low_means_dict = {}
high_means_dict = {}

for ridx, response in enumerate(responses):
    low_means_dict[response]  = []
    high_means_dict[response] = []

    for factor in factors:
        means = separate(factor, data_factors, data_list)
        mlen = int(len(means)/2)
        low_means_dict[response].append(means[ridx])
        high_means_dict[response].append(means[mlen+ridx])

    low_means  = copy(low_means_dict[response])
    high_means = copy(high_means_dict[response])

    # 1. Generate dummy DoE data for 6 factors (Low vs High levels)

    # 2. Set up the figure and grid (1 row, 6 columns)
    fig, axes = plt.subplots(1, 6, figsize=(14, 5), sharey=True)
    fig.suptitle(f"Main Effects Plot for Response Variable {response}", fontsize=14, fontweight="bold")

    # Calculate overall grand mean to add a reference line
    grand_mean = np.mean(low_means + high_means)

    # 3. Plot each factor
    for i, ax in enumerate(axes):
        # Plot the means for [-1, 1] or [Low, High]
        y_values = [low_means[i], high_means[i]]
        x_values = ["Low", "High"]
        
        # Plot line and markers
        ax.plot(x_values, y_values, marker="o", color="blue", linewidth=2, markersize=8)
        
        # Add horizontal grand mean reference line
        ax.axhline(grand_mean, color="red", linestyle="--", alpha=0.6)
        
        # Titles and formatting
        ax.set_title(factor_labels[i], fontsize=11, fontweight="semibold")
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        ax.set_xlim(-0.3, 1.3)

    # 4. Clean up axes and labels
    axes[0].set_ylabel(f"Mean Response Value {response}", fontsize=12)

    # Adjust layout to prevent overlap
    plt.tight_layout()

    # 5. Display the plot
    fname = f"mean-plot-{response_name[ridx]}" 
    plt.savefig(fname)

