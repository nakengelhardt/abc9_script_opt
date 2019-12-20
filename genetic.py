import random
import subprocess
import os
import hashlib
import re

### Parameter Definitions ###
generations = 20                # number of iterations that the algorithm runs
children_per_generation = 16    # number of scripts created for evaluation in every iteration
survivors_per_generation = 8    # number of scripts to keep after evaluation
assert(survivors_per_generation < children_per_generation)

mutation_chance = 0.1           # likelihood of the 'mutate' function introducing a mutation in a script
assert (mutation_chance >= 0 and mutation_chance < 1)
random_seed = 42                # for reproducibility. Set to None to get different results each run

initial_population = [          # Starting population. Initialize with some known good scripts
    ["&st;", "&scorr;", "&sweep;", "&dc2;", "&st;", "&dch -f;", "&if -W 300 -v;", "&mfs;"],
    ["&st;", "&sweep -v;", "&scorr;", "&st;", "&if -W 300;", "&save;", "&st;", "&syn2;", "&if -W 300 -v;", "&save;", "&load;", "&st;", "&if -g -K 6;", "&dch -f;", "&if -W 300 -v;", "&save;", "&load;", "&st;", "&if -g -K 6;", "&synch2;", "&if -W 300 -v;", "&save;", "&load;", "&mfs;"],
    ["&st;", "&synch2;", "&if -m -a -K 6 -W 300;", "&mfs;", "&st;", "&dch;", "&if -m -a -W 300 -v;", "&mfs;"]
]

### Benchmarks to use for evaluation ###
## small set for testing
bmarks = "bmarks/s27.v bmarks/s420.v"
## the whole iscas89 benchmark suite
# import glob
# bmarks = " ".join(glob.glob("bmarks/s*.v"))

### Mutating ###
# The 'mutate' function takes a script and introduces mutations with a certain probability.
# Modify this function to change how mutations are introduced.

commands = [
 "&st;", "&scorr;", "&sweep;", "&syn2;", "&synch2;",
 "&dc2;", "&dch -f;", "&mfs;",
 "&if -W 300;",
 "&if -W 300 -K 4;", "&if -W 300 -K 6;", "&if -W 300 -K 8;",
 "&if -g -K 4;", "&if -g -K 6;", "&if -g -K 8;",
 "&if -m -a -K 6 -W 300;", "&if -m -a -W 300;",
 "&save;", "&load;"
]

def random_command():
    return random.choice(commands)

def mutate(p, chance=0.1):
    for i in range(len(p)):
        if random.random() < chance:
            p[i] = random_command()
    return p

### Crossing ###
# The 'cross' function takes two scripts 'a' and 'b' and creates a new 'child' script that
# is a cross of the two. Modify this function to change how scripts are mixed together.

def cross(a, b):
    a_end = random.randrange(len(a))
    b_start = random.randrange(len(b))
    return a[:a_end] + b[b_start:]

### Attempt to make a script created by crossing + mutation conform to some rules. ###
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
    for i in range(len(c) - 1, -1, -1):
        if c[i] in ["&mfs;", "&save;", "&load;"]:
            continue
        if c[i].startswith("&if"):
            r = re.compile(" -K \d+")
            c[i] = r.sub('', c[i])
            if c[i].find(" -W 300") < 0:
                c[i] = c[i].replace(";", " -W 300;")
            if c[i].find(" -v") < 0:
                c[i] = c[i].replace(";", " -v;")
            return c
    return None

###################################################################
## Algorithm itself, should be no need to modify below this line ##
###################################################################

# sha1 hashes are used to identify scripts
def get_script_hash(script):
    s = " ".join(script)
    h = hashlib.sha1()
    h.update(s.encode())
    return h.hexdigest()


def make_next_gen(population, num=100, chance=0.1):
    children = []
    while len(children) < num-len(population):
        a = random.choice(population)
        b = random.choice(population)
        c = canonify(mutate(cross(a,b)))
        if c:
            children.append(c)
    children.extend(population) # keeping the last generations' best ensures that results don't get worse over time
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
            with open('{}/{}.abc9'.format(script_dir, get_script_hash(p)), 'w') as f:
                f.write(" ".join(p))

# run evaluation function on the current population
def run_eval():
    subprocess.run(['BMARKS="{}" /usr/bin/time make -j8 -f evaluate.mk'.format(bmarks)], shell=True)

# get score for script 'p'
# return value "None" indicates the script is defective in some way (e.g. crashes abc9)
def evaluate(p):
    try:
        with open('logs/{}.res'.format(get_script_hash(p))) as f:
            score = int(f.read())
            return score
    except (FileNotFoundError, ValueError):
        # if the file doesn't exist or does not contain a single int,
        # the script is not functional and should be removed from population.
        return None

# select the top scoring scripts
# smaller scores are better
def select_best(population, popcap=10):
    dump_pop(population)
    run_eval()
    survivors = []
    worst_score = None
    for p in population:
        score = evaluate(p)
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
    # print("Fittest: ")
    for k in sorted(survivors):
        population.append(k[1])
    #     print("{}\t{}\t{}".format(k[0], get_script_hash(k[1]), " ".join(k[1])))
    return population

def run(clean=True):
    # initialize the RNG
    if random_seed:
        random.seed(random_seed)

    if clean:
        # remove existing results that might have been generated with different benchmark set or evaluation function
        subprocess.run(['make -f evaluate.mk clean'], shell=True)

    # run the algorithm
    population = initial_population
    for g in range(generations):
        print("Evaluating generation {}...".format(g))
        population = make_next_gen(population, num=children_per_generation, chance=mutation_chance)
        # print("New population:")
        # for p in population:
        #     print("{}\t{}".format(get_script_hash(p), " ".join(p)))
        population = select_best(population, popcap=survivors_per_generation)
    print("Results:")
    for p in population:
        print("{} ({})".format(" ".join(p), get_script_hash(p)))

if __name__ == '__main__':
    run()
