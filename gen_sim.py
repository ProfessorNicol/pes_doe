import sys
import os
import json

from itertools import product
import subprocess

def generate_vectors( choices ):
    yield from product(*choices.values())


if len(sys.argv) != 2:
    print(f"Useage python gen_args.py gen_args_file")
    exit(1)

try:
    with open(sys.argv[1],'r') as rf:
        args_dict = json.load(rf)
except:
    print(f"Unable to open gen_args file {sys.argv[1]}")
    exit(1)

keys = list(args_dict)

try:
    os.remove("output.json")
except:
    pass

# iterate over all possible assignments of values to factors
for vector in generate_vectors(args_dict):

    # create a dictionary binding command line arguments to values,
    # and write into file 'args'

    result = dict(zip(keys, vector))
    with open("args", "w") as wf:
        for key, value in result.items():
            line = f"{key} {value}\n"
            wf.write(line)

    # create the command line needed to run a process.
    # equivalent to the strings on a bash command line

    cmdList = ["python3", "main.py", "-is", "args"]

    # create the process, making its stdout and stderr available to this script 

    process = subprocess.Popen(cmdList,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # run the process, capture stdout and stderr
    stdout, stderr = process.communicate()

    # complain and die if error encountered
    if process.returncode != 0:
        print("Error from simulation run")
        if len(stdout) > 0:
            print(stdout)

        if len(stderr) > 0 :
            print(stderr)

        exit(1)

    # run was successful so print out what it yielded from stdout and stderr

    if len(stdout) > 0:
        print(stdout)

    if len(stderr) > 0 :
        print(stderr)

