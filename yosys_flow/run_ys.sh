
#!/bin/bash

# Configuration
VERILOG_FILE="generated_module.v"
TOP_MODULE="logic_module"
TARGET_WIRE="success"
MAX_CYCLES=300

for cycles in $(seq 1 $MAX_CYCLES); do
    echo "Checking sequence length: $cycles cycles..."

    # Execute Yosys, passing the current loop iteration to -set-at
    yosys -p "
        read_verilog $VERILOG_FILE;
        hierarchy -top $TOP_MODULE;
        proc;
        async2sync;
        techmap;
        opt;
        sat -seq $cycles -set-at $cycles $TARGET_WIRE 1 -show-public;
    " > sat_output.log 2>&1

    # Check if the solver successfully asserted the wire
    if grep -q "SAT SOLVER RESULT: SATISFIABLE" sat_output.log; then
        echo "=================================================="
        echo "SUCCESS! Found a valid input sequence at cycle $cycles."
        echo "=================================================="
        # Extract and print the input sequence trace from the log
        sed -n '/Signal Name/,/failing/p' sat_output.log
        exit 0
    elif grep -q "ERROR:" sat_output.log; then
        echo "Yosys error encountered. Check sat_output.log"
        exit 1
    fi
done

echo "FAILED: '$TARGET_WIRE' did not go high within $MAX_CYCLES cycles."
exit 1
