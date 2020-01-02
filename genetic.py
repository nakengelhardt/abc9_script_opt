import random
import subprocess
import os
import hashlib
import re

### Parameter Definitions ###
generations = 20                # number of iterations that the algorithm runs
children_per_generation = 32    # number of scripts created for evaluation in every iteration
survivors_per_generation = 8    # number of scripts to keep after evaluation
assert(survivors_per_generation < children_per_generation)

mutation_chance = 0.2           # likelihood of the 'mutate' function introducing a mutation in a script
assert (mutation_chance >= 0 and mutation_chance < 1)
random_seed = 42                # for reproducibility. Set to None to get different results each run
num_proc = 8                    # number of parallel runs for make

# Note: The following scripts get canonified before use!

# Baseline. Results for this script can be used as a reference in the evaluation function
baseline = ["&st;", "&scorr;", "&sweep;", "&dc2;", "&st;", "&dch -f;", "&if -W 300 -v;"]

initial_population = [          # Starting population. Initialize with some known good scripts
    ["&st;", "&scorr;", "&sweep;", "&dc2;", "&st;", "&dch -f;", "&if -W 300 -v;", "&mfs;"],
    ["&st;", "&sweep -v;", "&scorr;", "&st;", "&if -W 300;", "&save;", "&st;", "&syn2;", "&if -W 300 -v;", "&save;", "&load;", "&st;", "&if -g -K 6;", "&dch -f;", "&if -W 300 -v;", "&save;", "&load;", "&st;", "&if -g -K 6;", "&synch2;", "&if -W 300 -v;", "&save;", "&load;", "&mfs;"],
    ["&st;", "&synch2;", "&if -m -a -K 6 -W 300;", "&mfs;", "&st;", "&dch;", "&if -m -a -W 300 -v;", "&mfs;"]
]

### Benchmarks to use for evaluation ###
## small set for testing
# benchmarks = ["bmarks/s27.v", "bmarks/s420.v"]
## the whole iscas89 benchmark suite
import glob
benchmarks = glob.glob("bmarks/s*.v") # (excludes dff.v)

## Where to find yosys
yosys_path = "/home/nak/Work/yosys-clean/yosys"

### Function Definitions ###

## Crossing ##
# The 'cross' function takes two scripts 'a' and 'b' and creates a new 'child' script that
# is a cross of the two. Modify this function to change how scripts are mixed together.

def cross(a, b):
    a_end = random.randrange(len(a))
    b_start = random.randrange(len(b))
    return a[:a_end] + b[b_start:]

## Mutating ##
# The 'mutate' function takes a script and introduces mutations with a certain probability.
# Modify this function to change how mutations are introduced.

commands = {
    "&if -W 300" : [[" -K 4", " -K 5", " -K 6", " -K 8"], " -m", " -g", " -x", " -a", [" -C 8", " -C 16", " -C 32", " -C 64"]],
    "&st" : [],
    "&scorr" : [],
    "&sweep" : [],
    "&syn2" : [],
    "&syn3" : [],
    "&syn4" : [],
    "&synch2" : [" -f"],
    "&dc2" : [],
    "&dch" : [" -f"],
    "&save" : [],
    "&load" : []
}

def random_command():
    cmd = random.choice([x for x in commands])
    res = cmd
    if commands[cmd]:
        k = random.randrange(len(commands[cmd])) #TODO: make higher values less likely
        for opt in random.sample(commands[cmd], k):
            if isinstance(opt, list):
                opt = random.choice(opt)
            res += opt
    return res + ";"

def mutate(p):
    for i in range(len(p)):
        if random.random() < mutation_chance:
            p[i] = random_command()
    return p

## Attempt to make a script created by crossing + mutation conform to some rules. ##
# The 'canonify' function can modify a new script in some way before adding it to the
# population. This is useful e.g. to ensure that abc9 always prints delay information for
# use in the evaluation function.
# This function can 'give up' on horribly malformed scripts by returning None,
# in which case a new random script is drawn to replace it. However, it should not be too
# strict, to avoid long loops trying to randomly generate scripts that conform to a
# specific pattern.
# There is no need to ensure that all scripts returned by this function are valid,
# as the fitness test will eliminate scripts that cause crashes or return invalid results.
# This function is optional: everything works if it simply returns the input unmodified.

def canonify(c):
    excluded_commands = {"&mfs;", "&ps;", "&ps -l;", "&verify -s;", "time;"}
    c = [x for x in c if x not in excluded_commands]
    last_if = True
    for i in range(len(c) - 1, -1, -1):
        if c[i] == "&save;":
            last_if = True
            continue
        if c[i].startswith("&if"):
            r = re.compile(" -W \d+")
            c[i] = r.sub(" -W 300", c[i])
            if c[i].find(" -W 300") < 0:
                c[i] = c[i].replace(";", " -W 300;")
            if last_if:
                r = re.compile(" -K \d+")
                c[i] = r.sub('', c[i])
                if c[i].find(" -v") < 0:
                    c[i] = c[i].replace(";", " -v;")
                last_if = False
            else:
                c[i] = c[i].replace(" -v", "")
    if "&save;" in c:
        if c[-1] != "&load;":
            if c[-1] != "&save;":
                c.append("&save;")
            c.append("&load;")
    c.append("time;")
    c.append("&verify -s;")
    return c

## Evaluation function
# This function has two arguments: the results for the script under consideration
# and the results for the baseline script. Both arguments are a dictionary with
# the elements of the 'benchmarks' list as keys. The values are dictioaries again,
# with one entry for each key-value pair returned by get_data.sh
# The values are kept as strings since they might be int/float or other. Please
# remember to cast them to the appropriate data type.
# Raise a ValueError here if some data is absent or not of the expected shape - it
# will be interpreted as the script not being functional (leading to removal
# from the population).

# TODO Example of data layout:

# NB: smaller return values are considered better!

from statistics import geometric_mean

def evaluate(script_res, baseline_res):
    delay = geometric_mean([int(script_res[b]["Del"])/int(baseline_res[b]["Del"]) for b in benchmarks])
    area = geometric_mean([int(script_res[b]["LCs"])/int(baseline_res[b]["LCs"]) for b in benchmarks])
    time = geometric_mean([float(script_res[b]["seconds"])/float(baseline_res[b]["seconds"]) for b in benchmarks])
    # abc "time" command doesn't have enough digits for smaller Benchmarks
    # use overall sum even if it's bad statistics
    return area * delay + 0.1 * time

###################################################################
## Algorithm itself, should be no need to modify below this line ##
###################################################################

# sha1 hashes are used to identify scripts
def get_script_hash(script):
    s = " ".join(script)
    h = hashlib.sha1()
    h.update(s.encode())
    return h.hexdigest()


def make_next_gen(survivors, num=100, chance=0.1):
    children = list()
    # keeping the last generations' best ensures that results don't get worse over time
    children.extend(survivors)
    while len(children) < num:
        a = random.choice(survivors)
        b = random.choice(survivors)
        c = canonify(mutate(cross(a,b)))
        if c and c not in children:
            children.append(c)
    return children

# write scripts in population to scripts directory
def dump_pop(population, script_dir='scripts'):
    if not os.path.exists(script_dir):
        os.mkdir(script_dir)
    assert(os.path.isdir(script_dir))
    for p in population:
        if not os.path.exists('{}/{}.abc9'.format(script_dir, get_script_hash(p))):
            # only write the script if it doesn't exist yet;
            # otherwise avoid touching the file so make doesn't re-run evaluation
            with open('{}/{}.abc9'.format(script_dir, get_script_hash(p)), 'x') as f:
                f.write(" ".join(p))

# run evaluation function on the current population
def run_eval():
    subprocess.run(['YOSYS={} BMARKS="{}" make -j{} -f evaluate.mk'.format(yosys_path, " ".join(benchmarks), num_proc)], shell=True)

def read_results(hash, log_dir='logs'):
    results = dict()
    for b in benchmarks:
        # this is probably a bit fragile, have to extract same name here as in evaluate.sh
        bname, bext = os.path.splitext(os.path.basename(b))
        with open("{}/{}_{}.res".format(log_dir, hash, bname)) as f:
            d = dict()
            for line in f:
                k,v = (x.strip() for x in line.split("=", maxsplit=1))
                d[k] = v
            results[b] = d
    return results

# get score for script 'p'
# return value "None" indicates the script is defective in some way (e.g. crashes abc9)
def get_score(script, log_dir='logs'):
    hash = get_script_hash(script)
    try:
        with open("{}/{}.res".format(log_dir, hash)) as f:
            t = f.read().strip()
            if t != "PASS":
                return None
            results = read_results(hash)
            return evaluate(results, baseline_result)
    except (FileNotFoundError, ValueError) as e:
        # if the file doesn't exist or does not contain the right values,
        # the script is not functional and should be removed from population.
        return None

def set_baseline():
    global baseline_result
    b = canonify(baseline)
    dump_pop([b])
    run_eval()
    baseline_result = read_results(get_script_hash(b))

# select the top scoring scripts
# smaller scores are better
def select_best(population, popcap=10):
    dump_pop(population)
    run_eval()
    survivors = []
    worst_score = None
    print("Score\tHash\tScript")
    for p in population:
        score = get_score(p)
        if score == None:
            print("--\t{}\t{}".format(get_script_hash(p), " ".join(p)))
        else:
            print("{:.2f}\t{}\t{}".format(score, get_script_hash(p), " ".join(p)))
        if score != None: # eliminate non-functional scripts
            if len(survivors) < popcap:
                survivors.append((score, p))
                if worst_score == None or worst_score < score:
                    worst_score = score
            elif worst_score > score:
                # find a script with the worst score and remove it, add this script instead
                # could instead keep the list sorted, but this is hardly the bottleneck
                for i in range(len(survivors)):
                    s, q = survivors[i]
                    if s == worst_score:
                        del survivors[i]
                        survivors.append((score, p))
                        worst_score = max(a for a,b in survivors)
                        break
    if not survivors:
        raise ValueError("No functional scripts in population.")

    population = []
    for k in sorted(survivors):
        population.append(k[1])
    return population

def run(clean=True):
    # initialize the RNG
    if random_seed != None:
        random.seed(random_seed)

    if clean:
        # remove existing results that might have been generated with different benchmark set or evaluation function
        subprocess.run(['make -f evaluate.mk clean'], shell=True)

    # get baseline
    set_baseline()

    # run the algorithm
    population = [canonify(x) for x in initial_population]
    for g in range(generations):
        print("Evaluating generation {}...".format(g))
        population = make_next_gen(population, num=children_per_generation, chance=mutation_chance)
        population = select_best(population, popcap=survivors_per_generation)
    print("Results:")
    for p in population:
        print("{} ({})".format(" ".join(p), get_script_hash(p)))

if __name__ == '__main__':
    run()
