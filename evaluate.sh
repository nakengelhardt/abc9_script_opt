set -e

script_hash="$1"

DEFAULT_BMARKS=*.il
BMARKS=${BMARKS:-$DEFAULT_BMARKS}
YOSYS=${YOSYS:-yosys}


for bmark in $BMARKS; do
	top=${bmark##*/}
	top=${top%.il}
	if ! ${YOSYS} -ql logs/${script_hash}_${top}.log -p "read_ilang ${bmark} ; \
	scratchpad -set abc9.scriptfile scripts/${script_hash}.abc9 ; \
	read_verilog -lib +/xilinx/cells_sim.v; read_verilog -lib +/xilinx/cells_xtra.v; \
	synth_xilinx -flatten -abc9 -run map_luts:end ;" &>/dev/null; then
		echo "FAIL" > logs/${script_hash}.res
		# echo "Script '$script_hash' is not functional."
		exit 0 # abort early
	fi
	./get_data.sh logs/${script_hash}_${top}.log > logs/${script_hash}_${top}.res
done
echo "PASS" > logs/${script_hash}.res
