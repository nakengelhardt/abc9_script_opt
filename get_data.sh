#!/usr/bin/env bash

if [ -z "$1" ]
then
	echo "Usage: $0 logfile" >&2
	exit 1
fi

logfile="$1"

grep -Eo "Del =[[:space:]]*[0-9]+" ${logfile} | tr -dc "[0-9]\n" | awk 'NR == 1 || $1 < min {min=$1} END {print "Del =", min}'
grep "Estimated number of LCs" ${logfile} | tr -dc "[0-9]\n" | awk '{s+=$1} END {print "LCs =", s}'
grep -Eo "ABC: elapse: [0-9]+([.][0-9]+)? seconds" ${logfile} | tr -dc "[0-9].\n" | awk '{s=$1} END {print "seconds =", s}'
