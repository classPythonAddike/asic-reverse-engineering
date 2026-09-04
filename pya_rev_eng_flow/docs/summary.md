# How We Solved the Jane Street ASIC Puzzle 2026

When I first opened `puzzle.gds`, it was immediately clear this wasn't a typical software reverse-engineering problem. Hardware state machines are dense, and standard EDA tools are built to go from code to layout—not the other way around.

My initial idea was to build a modular pipeline to extract the logic, synthesize it back into a readable format, and throw a SAT solver at it. The team came together around that approach, and here's a breakdown of how we built it, the roadblocks we hit, and how we finally cracked it.

---

## 1. Extracting the Logic from the Layout

Our first goal was to get a netlist out of the GDSII file. I wrote `01_extract_netlist.py` using KLayout's `pya` Python API to traverse the physical layers (poly, li1, and metal interconnects) and map out the standard cell instances and their connections. That gave us a raw JSON netlist.

But physical connections alone aren't enough—we needed to know which pins were inputs and which were outputs. The team wrote `02_parse_liberty.py` to parse the SKY130 Liberty file and map pin directions, which let us start reconstructing the Verilog.

**The first roadblock:** The raw netlist was full of physical-only cells—decoupling capacitors (`decap`), tap cells, via matrices. They completely cluttered the design. We updated our Verilog reconstruction script to filter out about 9,000 of these, leaving just the 728 logic-bearing gates we actually cared about.

## 2. Reverse Synthesis

With structural Verilog in hand, we needed to flatten the 27 hierarchical modules to analyze the state machine as a single unit. We fed it into Yosys via a custom script (`synth.ys`) to flatten and optimize away any dead logic.

**The second roadblock:** My original plan was to use Yosys' `write_eq` command to dump the boolean equations directly. It either failed silently or wasn't supported in our environment. Rather than spending days fighting the tool, we pivoted: use Yosys *only* for flattening, and I'd write a dedicated Python script to extract the boolean equations ourselves.

## 3. Extracting the Boolean Equations

I wrote `extract_bool_exprs.py` to parse the flattened gate-level Verilog. It recursively traces backward from the D-input of every flip-flop to build a symbolic logic graph (DAG) for the next state.

A couple of things tripped us up:
- Yosys prefixed all cell names with `sky130_fd_sc_hd__`, which broke the parser outright. A quick strip of that prefix in the parsing loop fixed it.
- We also hit combinatorial loops. Tracing logic backward in an optimized netlist can introduce circular dependencies; the team worked through a multi-pass fixpoint resolver to make sure all paths terminated.

Eventually we had a clean `bool_exprs.txt` with next-state equations for all 86 flip-flops.

## 4. The SAT Solver Explosion

With the equations extracted, the team modeled the FSM in Z3 to find an input sequence that drives `success` high.

**The biggest roadblock:** My first solver used naive string substitution to unroll the state machine cycle-by-cycle. Shared sub-expressions (like a common AND gate) got duplicated for every downstream connection. Memory usage ballooned exponentially, ate gigabytes in seconds, and crashed Z3 entirely.

**The fix:** I rewrote the solver as `fast_tseitin.py`, implementing a proper Tseitin Transformation. By introducing an intermediate Z3 variable for every gate in the logic DAG, memory usage scaled linearly instead of exponentially. Z3 tore through the unrolled cycles in seconds.

## 5. Testing on the Warmup Circuit

Before trusting the pipeline on the main puzzle, I insisted the team validate everything on the provided `warmup` circuit first.

Glad we did. The warmup exposed two real bugs:
1. The expression evaluator choked on ternary operators (`? :`), which the warmup's shift registers used throughout.
2. Our bit-ordering assumption (MSB vs. LSB) was completely backward.

Working through both on a small, known circuit gave the team confidence that the extractor and simulator were physically accurate before we committed to the main run.

## 6. Getting the Final Answer

With the pipeline solid, we ran the SAT solver on the full puzzle logic. Z3 proved the state machine reaches `success = 1` at exactly **cycle 123** and returned the required 123-bit input sequence.

To close the loop, the team wrote a cycle-accurate Python simulator (`simulate.py`) that re-runs the raw extracted boolean logic against that sequence.

At cycle 123, the simulator confirmed `success = True`. The 8 primary output pins evaluated to `01011001` (decimal **89**)—ASCII **`'Y'`**.

---

## Alternative Approaches

The Z3 SAT solver worked cleanly for us, but there were other valid directions we considered:

1. **Visual Inspection**: Tracing the clock tree in KLayout is a fast way to locate all state elements and get an intuition for the FSM structure before writing a single line of code.
2. **Structural Partitioning**: Instead of unrolling all 86 flip-flops, the team could have scanned the netlist for recognizable patterns—shift registers, ripple counters—to shrink the search space dramatically.
3. **Simulation-based fuzzing**: A Verilog testbench with random input sequences, observed in GTKWave, is a classic and practical first step to distinguish a sequence detector from a simple timer.

Any of these would have been valid starting points; the modular pipeline we built just happened to be the most direct path to a verifiable answer.
