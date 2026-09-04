# Jane Street ASIC Puzzle 2026 — Solution & Tooling

This repo contains the scripts and documentation our team put together to solve the Jane Street ASIC Puzzle.

The challenge: reverse-engineer a hardware state machine from a raw GDSII layout (`puzzle.gds`), figure out the logic, and find a 123-bit input sequence that drives the `success` pin high.

## What's inside

- **`scripts/`**: The Python scripts and Yosys files used to pull the logic out of the GDSII file, plus the Z3 SAT solver that found the winning sequence.
- **`docs/`**: A writeup covering the approach, the roadblocks we hit, and how we worked around them.
- **`results/`**: The final 123-bit sequence (`solution.txt`) and a simulation trace (`light_trace.json`) that proves it works.

## How the pipeline works

I designed a reverse-EDA pipeline to turn the physical layout into a SAT-solvable graph. The team built and debugged each stage together. Here's the general flow:

1. `00_inspect_gds.py`: Inspects the GDSII hierarchy and identifies standard cells.
2. `01_extract_netlist.py`: Pulls a hierarchical JSON netlist from the metal layers using KLayout's `pya` API.
3. `02_parse_liberty.py`: Parses the SKY130 Liberty file to determine pin directions (input vs. output).
4. `04_netlist_to_verilog.py`: Reconstructs structural Verilog. We added filtering here to drop physical-only cells like decaps and tap cells (~9,000 of them).
5. `synth.ys`: A Yosys script that flattens and optimizes the Verilog into a clean gate-level netlist.
6. `extract_bool_exprs.py`: Parses the gate-level Verilog and extracts next-state logic equations for all flip-flops and outputs.
7. `fast_tseitin.py`: The Z3 SAT solver. I used a Tseitin Transformation to model the unrolled state machine without blowing up memory.
8. `simulate.py`: A cycle-accurate Python simulator the team wrote to verify the solved sequence drives `success = 1`.

## The Solution

The SAT solver proved the state machine reaches `success = 1` exactly at **cycle 123**.

**The Input Sequence:**
`000000010101000010000000000001010101000000000000101000000100000100000010000010100001000000010000001000001001000101000000010`

At cycle 123, the 8-bit output (`O_7..O_0`) evaluates to `01011001` (decimal **89**)—ASCII **`'Y'`**.

## Documentation

For a full breakdown of how I designed the pipeline and the debugging process the team worked through, see:
- `docs/summary.md`
