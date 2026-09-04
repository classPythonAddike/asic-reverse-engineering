# How we Solved the Jane Street ASIC Puzzle 2026

When we first opened `puzzle.gds`, we realized pretty quickly that we couldn't just treat it like a typical software reverse-engineering problem. Hardware state machines are dense, and standard EDA tools are built to go from code to layout—not the other way around. 

So, we decided to build a modular pipeline to extract the logic, synthesize it back into a readable format, and throw a SAT solver at it. Here’s a breakdown of how we put it all together, the issues we ran into, and how we finally got the answer.

---

## 1. Extracting the Logic from the Layout

Our first goal was to get a netlist out of the GDSII file. We wrote `01_extract_netlist.py` using KLayout's Python API to traverse the physical layers (like poly and metal interconnects) and map out the standard cell instances and their connections. That gave me a raw JSON netlist.

But physical connections alone aren't enough—we needed to know which pins were inputs and which were outputs. We wrote a parser (`02_parse_liberty.py`) for the SKY130 Liberty file to map everything out and started reconstructing the Verilog.

**The first roadblock:** The raw netlist was full of physical-only cells like decoupling capacitors (`decap`), tap cells, and via matrices. They were completely cluttering the design. We had to update our Verilog script to filter out about 9,000 of these useless cells, which left us with just the 728 logic-bearing gates we actually cared about.

## 2. Reverse Synthesis

Now that we had structural Verilog, we needed to flatten the 27 hierarchical modules so we could analyze the state machine as a single unit. we fed it into Yosys using a custom script (`synth.ys`) to flatten and optimize away dead logic.

**The second roadblock:** My original plan was to use Yosys' `write_eq` command to just dump the boolean equations for me. Unfortunately, it either failed or wasn't supported in my environment. Instead of spending days fighting an EDA tool, we pivoted. we decided to use Yosys *only* for flattening the netlist, and I'd write my own Python script to extract the boolean equations.

## 3. Extracting the Boolean Equations

I wrote a custom script (`extract_bool_exprs.py`) to parse the flattened gate-level Verilog. It recursively traces backward from the D-input of every flip-flop to build a symbolic logic graph (DAG) for the next state.

I hit a few snags here:
- Yosys prefixed all the cell names with `sky130_fd_sc_hd__`, which broke my parser. A quick `sed` script fixed that.
- we also ran into combinatorial loops. Tracing logic backward in an optimized netlist can sometimes cause circular dependencies, so we had to write a multi-pass resolver to make sure all paths terminated correctly.

Eventually, this gave me a clean `bool_exprs.txt` file with the next-state equations for all 92 flip-flops.

## 4. The SAT Solver Explosion

With the equations extracted, we modeled the FSM in Z3 to find a sequence where the `success` pin went high. 

**The biggest roadblock:** My first solver script used naive string substitution to unroll the state machine cycle by cycle. This meant that shared sub-expressions (like a common AND gate) were duplicated for every downstream connection. The expressions grew exponentially, ate gigabytes of RAM in seconds, and crashed Z3.

**The fix:** we wrote a new solver (`fast_tseitin.py`) that implemented a Tseitin Transformation. By introducing intermediate Z3 variables for every single internal gate in my logic DAG, memory usage scaled linearly instead of exponentially. Z3 was suddenly able to chew through the unrolled cycles in seconds.

## 5. Testing on the Warmup Circuit

Before trusting my pipeline on the main puzzle, we forced myself to test everything on the provided `warmup` circuit. 

I'm glad we did. Running the warmup exposed some serious bugs:
1. My Python expression evaluator failed to parse ternary operators (`? :`), which the warmup's shift registers used heavily. 
2. My assumptions about bit-ordering (MSB vs. LSB) were backward.

Debugging these edge cases on a simple, known circuit gave me the confidence that my custom logic extractor and simulator were physically accurate.

## 6. Getting the Final Answer

With the pipeline hardened, we ran my SAT solver on the main puzzle logic. Z3 proved that the state machine reaches the `success` state at **cycle 123** and spat out the required 123-bit sequence of 1s and 0s.

To verify it, we wrote a cycle-accurate Python simulator (`simulate.py`) that executes the raw extracted boolean logic. 

At cycle 123, the simulator confirmed `success = True`. The 8 primary output pins evaluated to the binary string `01011001` (decimal **89**), which corresponds to the ASCII character **`'Y'`**.

---

## Alternative Approaches

While the Z3 SAT solver worked perfectly, we could have approached this more interactively instead of treating it like a math problem:

1. **Visual Inspection**: Opening the GDS in KLayout and tracing the clock tree is a great way to instantly identify all the state elements.
2. **Structural Partitioning**: Instead of unrolling 92 flip-flops, we could have parsed the netlist to look for recognizable patterns like shift registers or counters. 
3. **Simulation**: Writing a Verilog testbench and fuzzing random inputs while watching GTKWave is a classic way to figure out if a block of logic is a sequence detector or just a basic timer.

By identifying semantic structures, you can usually shrink the search space dramatically and turn a brute-force problem into a localized logic puzzle.
