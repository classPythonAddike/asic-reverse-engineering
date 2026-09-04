yosys -import

set max_cycles 300
set found 0

for {set i 1} {$i <= $max_cycles} {incr i} {
    # Restore the clean compiled design state from our backup slot instantaneously
    yosys design -copy-from compiled_base

    echo "----------------------------------------"
    echo "Testing SAT sequence window length: $i"
    echo "----------------------------------------"

    # Run SAT on the current cycle depth. 
    # catch prevents Yosys from crashing/exiting when the solver returns UNSAT
    if {[catch {yosys sat -seq $i -set-at $i success 1 -show-public} msg] == 0} {
        echo "=================================================="
        echo "SUCCESS! Valid input sequence found at cycle $i."
        echo "=================================================="
        set found 1
        break
    }
}

if {$found == 0} {
    error "FAILED: 'success' wire did not go high within $max_cycles cycles."
}
