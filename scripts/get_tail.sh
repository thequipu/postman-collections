#!/usr/bin/env bash
# Run on EC2: bash get_tail.sh
# Finds the latest test log and writes the last 80 lines to tail_output.txt
LATEST=$(ls -td reports/neuro-graph-test/*/test.log 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
  echo "No test logs found"
  exit 1
fi
echo "Latest log: $LATEST"
tail -80 "$LATEST" > tail_output.txt
echo "Written to tail_output.txt"
cat tail_output.txt
