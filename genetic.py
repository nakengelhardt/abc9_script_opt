import random
import subprocess
import os
import hashlib
import re
import glob

### Parameter Definitions ###
generations = 20                # number of iterations that the algorithm runs
children_per_generation = 32    # number of scripts created for evaluation in every iteration
survivors_per_generation = 8    # number of scripts to keep after evaluation
assert(survivors_per_generation < children_per_generation)

mutation_chance = 0.2           # likelihood of the 'mutate' function introducing a mutation in a script
assert (mutation_chance >= 0 and mutation_chance < 1)
random_seed = 42                # for reproducibility. Set to None to get different results each run
num_proc = 8                    # number of parallel runs for make

yosys_path = "yosys"            # Where to find yosys

benchmarks = []                 # Benchmarks to use for evaluation
benchmarks = glob.glob("bmarks/*.ys")               # the whole iscas89 benchmark suite
#benchmarks = ["bmarks/s27.ys", "bmarks/s420.ys"]    # (small set for testing)

### Note: The following scripts get canonified before use!

# Baseline. Results for this script can be used as a reference in the evaluation function
baseline = ["&scorr", "&sweep", "&dc2", "&st", "&dch -f", "&if -W 300; &mfs"]

# Starting population. Initialize with some known good scripts
initial_population = [
    baseline,
    ["&sweep", "&scorr", "&st; &if -W 300; &save", "&st", "&syn2", "&if -W 300; save; &load", "&st", "&if -g -K 6", "&dch -f", "&if -W 300; &save; &load", "&st; &if -g -K 6", "&synch2", "&if -W 300; &save; &load", "&mfs"],
    ["&synch2", "&if -m -a -K 6 -W 300; &mfs", "&st", "&dch", "&if -m -a -W 300; &mfs"]
]

# Possible mutations
mutations = {
    "&unmap; &if -W 300" : [[" -K 4", " -K 5", " -K 6", " -K 8"], " -m", " -a", [" -C 16", " -C 32", " -C 64"], ["; &mfs", "; &save; &mfs"], ["; &save", "; &save; &load"]],
    "&st" : [],
    "&scorr" : [],
    "&sweep" : [],
    "&syn2" : [],
    "&syn3" : [],
    "&syn4" : [],
    "&synch2" : [" -f"],
    "&dc2" : [],
    "&dch" : [" -f"],
}

## Evaluation function
# This function has two arguments: the results for the script under consideration
# and the results for the baseline script. Both arguments are a dictionary with
# the elements of the 'benchmarks' list as keys. The values are dictionaries again,
# with one entry for each key-value pair returned by get_data.sh
# The values are kept as strings since they might be int/float or other. Please
# remember to cast them to the appropriate data type.
# Raise a ValueError here if some data is absent or not of the expected shape - it
# will be interpreted as the script not being functional (leading to removal
# from the population).

# Example of data layout:
# {'bmarks/s27.ys': {'Del': '1010', 'LCs': '4', 'seconds': '0.01'},
# 'bmarks/s420.ys': {'Del': '2151', 'LCs': '27', 'seconds': '0.01'}}

# NB: smaller return values are considered better!

# https://stackoverflow.com/a/56229050
import math
def geometric_mean(xs):
        return math.exp(math.fsum(math.log(x) for x in xs) / len(xs))

def evaluate(script_res, baseline_res):
    delay = geometric_mean([int(script_res[b]["Del"])/int(baseline_res[b]["Del"]) for b in benchmarks])
    area = geometric_mean([int(script_res[b]["LCs"])/int(baseline_res[b]["LCs"]) for b in benchmarks])

    # watch out for too small benchmarks -- if the baseline execution time is less than 0.01s,
    # this will raise a ValueError and all scripts will be considered nonfunctional
    time = geometric_mean([max(0.01,float(script_res[b]["seconds"])) / max(0.01, float(baseline_res[b]["seconds"])) for b in benchmarks])

    return area * delay #+ 0.01 * time


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

def random_command():
    cmd = random.choice([x for x in mutations])
    res = cmd
    if mutations[cmd]:
        k = random.randrange(len(mutations[cmd])) #TODO: make higher values less likely
        # Sample k indices (sorted)
        indices = sorted(random.sample(range(len(mutations[cmd])), k))
        sample = [mutations[cmd][i] for i in indices]
        # If sample is a lists, pick one element
        sample = [random.choice(i) if isinstance(i, list) else i for i in sample]
        res += ''.join(sample)
    return res

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
    # Remove these commands
    blacklist = {"&verify -s", "time"}
    c = [x for x in c if x not in blacklist]

    # Find indices of all "&if" entries
    ifs = [i[0] for i in enumerate(c) if "&if" in i[1]]
    # If no "&if" entries, add one at the end
    if not ifs:
        ifs.append(len(c))
        c.append("&if -W 300")

    # Now make sure that only the whitelisted mutations follow the last "&if"
    last_if = ifs[-1]
    whitelist = {"&mfs", "&save", "&save; &load"}
    c = c[:last_if+1] + [x for x in c[last_if+1:] if x in whitelist]

    # If "&save" is used anywhere in the script and it doesn't end with '&save; &load',
    # add one to the end
    s = ' '.join(c)
    if '&save' in s and not s.endswith('&save; &load'):
        c.append('&save; &load')

    # Add these commands last
    c.append("time")
    #c.append("&verify -s")
    return c

###################################################################
## Algorithm itself, should be no need to modify below this line ##
###################################################################

# sha1 hashes are used to identify scripts
def get_script_hash(script):
    s = "\n".join(script)
    h = hashlib.sha1()
    h.update(s.encode())
    return h.hexdigest()


def make_next_gen(survivors, num, chance):
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
def write_abc9_script(population, script_dir='scripts'):
    if not os.path.exists(script_dir):
        os.mkdir(script_dir)
    assert(os.path.isdir(script_dir))
    for p in population:
        if not os.path.exists('{}/{}.abc9'.format(script_dir, get_script_hash(p))):
            # only write the script if it doesn't exist yet;
            # otherwise avoid touching the file so make doesn't re-run evaluation
            with open('{}/{}.abc9'.format(script_dir, get_script_hash(p)), 'x') as f:
                f.write("\n".join(p))

def run_eval_worker(args):
    script, bmark = args
    scripthash = os.path.splitext(os.path.basename(script))[0]

    dirname = os.path.dirname(bmark)
    basename = os.path.splitext(os.path.basename(bmark))[0]
    il = os.path.join(dirname, basename + ".il")

    res = "logs/{}_{}.res".format(scripthash, basename)
    if os.path.exists(res):
        return

    r = subprocess.run('{} -ql logs/{}_{}.log -p "\
            read_ilang {}; \
            scratchpad -set abc9.script {} ; \
            read_verilog -lib -specify +/xilinx/cells_sim.v +/xilinx/cells_xtra.v; \
            synth_xilinx -flatten -abc9 -dff -run map_luts:end; \
            sta; \
            "'.format(yosys_path, scripthash, basename, il, script), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if r.returncode != 0:
        with open(res, "w") as f:
            f.write("FAIL")
        return

    subprocess.run(r'''sed -n \
            -e "s/Latest arrival time in '.\+' is \([0-9]\+\):/Del = \1/p" \
            -e "s/\s\+Estimated number of LCs:\s\+\([0-9]\+\)/LCs = \1/p" \
            -e "s/ABC: .* total: \([0-9]\+\(.[0-9]\+\)\?\) seconds/seconds = \1/p" \
            logs/{0}_{1}.log > logs/{0}_{1}.res \
            '''.format(scripthash, basename), shell=True)

# run evaluation function on the current population
import multiprocessing
def run_eval(population):
    scripts = ['{}/{}.abc9'.format('scripts', get_script_hash(p)) for p in population]
    with multiprocessing.Pool(processes=num_proc) as pool:
        pool.map(run_eval_worker, ((i,j) for i in scripts for j in benchmarks))

    for p in population:
        fail = False
        for b in benchmarks:
            basename = os.path.splitext(os.path.basename(b))[0]
            with open('logs/{}_{}.res'.format(get_script_hash(p), basename)) as f:
                if f.read() == "FAIL":
                    fail = True
                    break
        with open('logs/{}.res'.format(get_script_hash(p)), 'w') as f:
            f.write('FAIL' if fail else 'PASS')

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
            if f.read() != "PASS":
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
    write_abc9_script([b])
    run_eval([b])
    baseline_result = read_results(get_script_hash(b))

# select the top scoring scripts
# smaller scores are better
def select_best(population, popcap):
    write_abc9_script(population)
    run_eval(population)
    survivors = []
    worst_score = None
    print("Score\tHash\t\tScript")
    output = []
    for p in population:
        score = get_score(p)
        if score == None:
            output.append((float("inf"),"--\t{}\t\t{}".format(get_script_hash(p)[:7], "; ".join(p))))
        else:
            output.append((score,("{:.2f}\t{}\t\t{}".format(score, get_script_hash(p)[:7], "; ".join(p)))))
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
    for _,o in sorted(output):
        print(o)
    if not survivors:
        raise ValueError("No functional scripts in population.")

    population = []
    for k in sorted(survivors):
        population.append(k[1])
    return population

def setup_worker(bmark):
    dirname = os.path.dirname(bmark)
    basename = os.path.splitext(os.path.basename(bmark))[0]
    il = os.path.join(dirname, basename + ".il")
    if os.path.exists(il):
        return
    print("Generating {}...".format(il))
    subprocess.run('{} -ql logs/{}_il.log -p "\
            script {}; \
            synth_xilinx -flatten -abc9 -dff -run begin:map_luts; \
            write_ilang {}; \
            "'.format(yosys_path, basename, bmark, il), shell=True)

def setup():
    if not os.path.exists("logs"):
        os.mkdir("logs")

    with multiprocessing.Pool(processes=num_proc) as pool:
        pool.map(setup_worker, benchmarks)

import shutil
import time
def run(clean):
    # initialize the RNG
    if random_seed != None:
        random.seed(random_seed)

    if clean:
        shutil.rmtree('logs')
        shutil.rmtree('scripts')

    setup()

    # get baseline
    set_baseline()

    # run the algorithm
    population = [canonify(x) for x in initial_population]
    for g in range(generations):
        start = time.time()
        print("Evaluating generation {}/{}...".format(g+1,generations))
        population = make_next_gen(population, num=children_per_generation, chance=mutation_chance)
        population = select_best(population, popcap=survivors_per_generation)
        print("Took {} seconds on {} procs".format(int(time.time()-start), num_proc))

import argparse
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ABC9 script tuning by genetic algorithm')
    parser.add_argument('--clean', action='store_true')
    args = parser.parse_args()
    run(clean=args.clean)
