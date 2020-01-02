YOSYS?=yosys

BMARK_FOLDER=bmarks/
BMARKS?=$(wildcard $(BMARK_FOLDER)s*.v)
ILFILES:=$(BMARKS:.v=.il)

SCRIPTFILES:=$(wildcard scripts/*.abc9)
SCRIPTS:=$(basename $(notdir $(SCRIPTFILES)))
LOGS:=$(foreach s,$(SCRIPTS),logs/$(s).log)
RESULTS:=$(foreach s,$(SCRIPTS),logs/$(s).res)

all: results

results: $(RESULTS)

ilangs: $(ILFILES)

logs/%.res: scripts/%.abc9 $(ILFILES) | logs
	@YOSYS="$(YOSYS)" BMARKS="$(ILFILES)" ./evaluate.sh $*

$(BMARK_FOLDER)%.il: $(BMARK_FOLDER)%.v | logs
	@echo "Generating $@..."
	@$(YOSYS) -ql logs/$*_il.log -p "read_verilog $(BMARK_FOLDER)dff.v; \
	read_verilog $<; \
	synth_xilinx -flatten -abc9 -run begin:map_luts; \
	write_ilang $@"

logs:
	mkdir -p logs

clean:
	rm -rf logs/ scripts/

.PHONY: all clean results ilangs
