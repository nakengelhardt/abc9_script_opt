YOSYS?=yosys

BMARK_FOLDER=bmarks/
BMARKS?=$(wildcard $(BMARK_FOLDER)*.ys)
ILFILES:=$(BMARKS:.ys=.il)

SCRIPTFILES:=$(wildcard scripts/*.abc9)
SCRIPTS:=$(basename $(notdir $(SCRIPTFILES)))
LOGS:=$(foreach s,$(SCRIPTS),logs/$(s).log)
RESULTS:=$(foreach s,$(SCRIPTS),logs/$(s).res)

all: results

results: $(RESULTS)

ilangs: $(ILFILES)

logs/%.res: scripts/%.abc9 $(ILFILES) | logs
	@YOSYS="$(YOSYS)" BMARKS="$(ILFILES)" ./evaluate.sh $*

$(BMARK_FOLDER)%.il: $(BMARK_FOLDER)%.ys | logs
	@echo "Generating $@..."
	$(YOSYS) -ql logs/$*_il.log -p "script $<; \
	synth_xilinx -flatten -abc9 -run begin:map_luts; \
	write_ilang $@"

logs:
	mkdir -p logs

clean:
	rm -rf logs/ scripts/

.PHONY: all clean results ilangs
