
from pyosys import libyosys as ys

# 1. Initialize design and read module files
design = ys.RTLIL.Design()
ys.run_pass("read_verilog generated_module.v", design)
ys.run_pass("hierarchy -top logic_module", design)

# 2. Run your synthesis and preparation passes
ys.run_pass("proc", design)
ys.run_pass("async2sync", design)
ys.run_pass("techmap", design)
ys.run_pass("opt", design)

# 3. Dynamic Python loop up to 300 cycles
max_cycles = 300
for cycles in range(1, max_cycles + 1):
    print(f"Checking sequence length: {cycles} cycles...")
    
    # We must push and pop the design state so the SAT solver doesn't accumulate constraints
    ys.run_pass("design -push", design)
    
    # Run the SAT command on the current cycle count
    sat_cmd = f"sat -seq {cycles} -set-at {cycles} success 1 -show-public"
    
    # Executing the command catches errors or checks satisfaction status
    try:
        ys.run_pass(sat_cmd, design)
        print(f"SUCCESS! Found a valid sequence at cycle {cycles}.")
        break
    except RuntimeError:
        # Yosys throws an exception if the SAT solver returns UNSATISFIABLE
        ys.run_pass("design -pop", design)
        continue
