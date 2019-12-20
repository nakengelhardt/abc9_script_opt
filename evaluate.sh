set -e

script_hash="$1"

DEFAULT_BMARKS=*.il
BMARKS=${BMARKS:-$DEFAULT_BMARKS}
YOSYS=${YOSYS:-~/Source/yosys/yosys}



rm -f logs/${script_hash}.stat logs/${script_hash}.time
for bmark in $BMARKS; do
	top=${bmark##*/}
	top=${top%.il}
	if ! ${YOSYS} -ql logs/${script_hash}_${top}.log -p "read_ilang ${bmark} ; \
	scratchpad -set abc9.scriptfile scripts/${script_hash}.abc9 ; \
	synth_xilinx -flatten -abc9 -run map_luts:end ; \
	tee -q -a logs/${script_hash}.stat stat -tech xilinx" &>/dev/null; then
		echo "" > logs/${script_hash}.res
		echo "Script '$script_hash' is not functional."
		exit 0
	fi
	egrep -o "Del =[[:space:]]*[0-9]+" logs/${script_hash}_${top}.log | tail -1 | tr -dc "[0-9]" >> logs/${script_hash}.time
	echo "" >> logs/${script_hash}.time
	echo "Evaluated script '$script_hash'."
done
#cat logs/${script_hash}.stat | grep "Estimated number of LCs" | tr -dc "[0-9]\n" | awk '{s+=$1} END {print s}' > logs/${script_hash}.res
cat logs/${script_hash}.time | awk '{s+=$1} END {print s}' > logs/${script_hash}.res
