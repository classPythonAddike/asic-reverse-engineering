# Jane Street ASIC Puzzle 2026 - Solution & Tooling

Here are the scripts and documentation I put together to solve the Jane Street ASIC Puzzle.

The challenge was to reverse-engineer a hardware state machine from a raw GDSII layout (`puzzle.gds`), figure out the logic, and find a 123-bit input sequence that drives the `success` pin high. 

## What's inside

- **`scripts/`**: The Python scripts and Yosys files I used to pull the logic out of the GDSII file, plus the Z3 SAT solver that found the winning sequence.
- **`docs/`**: A summary of my approach, the roadblocks I hit, and how I worked around them.
- **`results/`**: The final 123-bit sequence (`solution.txt`) and a simulation trace (`light_trace.json`) that proves it works.

## How the pipeline works

I built a reverse-EDA pipeline to turn the physical layout into a SAT-solvable graph. Here's the general flow:

1. `00_inspect_gds.py`: A quick script to inspect the GDSII hierarchy and standard cells.
2. `01_extract_netlist.py`: Pulls a hierarchical JSON netlist from the metal layers using KLayout's API.
3. `02_parse_liberty.py`: Parses the SKY130 Liberty file so I could figure out which pins were inputs and which were outputs.
4. `04_netlist_to_verilog.py`: Reconstructs the structural Verilog. I had to add some filtering here to drop physical-only cells like decaps and tap cells.
5. `synth.ys`: A Yosys script that flattens and optimizes the Verilog into a clean gate-level netlist.
6. `extract_bool_exprs.py`: Parses the gate-level Verilog and extracts the logic equations for all the flip-flops and outputs.
7. `fast_tseitin.py`: A Z3 SAT solver. I had to use a Tseitin Transformation here to model the unrolled state machine without blowing up my RAM.
8. `simulate.py`: A cycle-accurate Python simulator I wrote to run the extracted logic against the solved input sequence and verify the `success` state.

## The Solution

Running the SAT solver proved that the state machine reaches `success = 1` exactly at **cycle 123**.

**The Input Sequence:**
`000000010101000010000000000001010101000000000000101000000100000100000010000010100001000000010000001000001001000101000000010`

At cycle 123, the 8-bit output (`O_7..O_0`) evaluates to `01011001` (decimal **89**), which gives us the ASCII character **`'Y'`**.

## Documentation

If you're curious about how I built the pipeline or want to read about the debugging process, check out the writeup in the `docs/` folder:
- `summary.md`
