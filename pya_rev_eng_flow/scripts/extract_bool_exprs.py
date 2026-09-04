#!/usr/bin/env python3
"""
extract_bool_exprs.py
---------------------
Parses a Yosys-generated gate-level Verilog netlist (Sky130 hd cell library)
and outputs:
  1. Boolean expressions for each primary output in terms of primary inputs
     and current FF state variables (Q_<net>).
  2. Next-state equations D = f(...) for every flip-flop.

Usage:
    python3 extract_bool_exprs.py [netlist.v] [-o output.txt]

Verified Sky130 hd port name quirks:
  xnor2_2:  output port is Y  (not X)
  mux2_1:   inputs are A0 (S=0), A1 (S=1), S;  output X
  and2b_2:  inverted input A_N, non-inverted B
  nand2b_2: inverted input A_N, non-inverted B
"""

import re
import sys

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def wrap(s):
    """Wrap compound expression in parens."""
    if s and (' ' in s or (s[0] != '(' and '(' in s)):
        return f'({s})'
    return s


# ---------------------------------------------------------------------------
# Cell definitions: maps cell_type -> lambda(port_value_dict) -> (out_port, expr)
# The lambda receives a dict of port_name -> expression_string
# and returns a list of (output_port_name, expression_string)
# ---------------------------------------------------------------------------

CELL_DEFS = {
    # Buffers / Inverters
    'inv_2':        lambda p: [('Y', f'~{wrap(p["A"])}')],
    'buf_2':        lambda p: [('X', p['A'])],
    'clkbuf_16':    lambda p: [('X', p['A'])],
    'clkbuf_8':     lambda p: [('X', p['A'])],

    # AND family
    'and2_2':    lambda p: [('X', f'{wrap(p["A"])} & {wrap(p["B"])}')],
    'and2b_2':   lambda p: [('X', f'~{wrap(p["A_N"])} & {wrap(p["B"])}')],
    'and3_2':    lambda p: [('X', f'{wrap(p["A"])} & {wrap(p["B"])} & {wrap(p["C"])}')],
    'and3b_2':   lambda p: [('X', f'~{wrap(p["A_N"])} & {wrap(p["B"])} & {wrap(p["C"])}')],
    'and4_2':    lambda p: [('X', f'{wrap(p["A"])} & {wrap(p["B"])} & {wrap(p["C"])} & {wrap(p["D"])}')],
    'and4b_2':   lambda p: [('X', f'~{wrap(p["A_N"])} & {wrap(p["B"])} & {wrap(p["C"])} & {wrap(p["D"])}')],
    'and4bb_2':  lambda p: [('X', f'~{wrap(p["A_N"])} & ~{wrap(p["B_N"])} & {wrap(p["C"])} & {wrap(p["D"])}')],

    # NAND family
    'nand2_2':   lambda p: [('Y', f'~({wrap(p["A"])} & {wrap(p["B"])})')],
    'nand2b_2':  lambda p: [('Y', f'~(~{wrap(p["A_N"])} & {wrap(p["B"])})')],
    'nand3_2':   lambda p: [('Y', f'~({wrap(p["A"])} & {wrap(p["B"])} & {wrap(p["C"])})')],
    'nand3b_2':  lambda p: [('Y', f'~(~{wrap(p["A_N"])} & {wrap(p["B"])} & {wrap(p["C"])})')],
    'nand4_2':   lambda p: [('Y', f'~({wrap(p["A"])} & {wrap(p["B"])} & {wrap(p["C"])} & {wrap(p["D"])})')],

    # OR family
    'or2_2':     lambda p: [('X', f'{wrap(p["A"])} | {wrap(p["B"])}')],
    'or3_2':     lambda p: [('X', f'{wrap(p["A"])} | {wrap(p["B"])} | {wrap(p["C"])}')],
    'or3b_2':    lambda p: [('X', f'{wrap(p["A"])} | {wrap(p["B"])} | ~{wrap(p["C_N"])}')],
    'or4_2':     lambda p: [('X', f'{wrap(p["A"])} | {wrap(p["B"])} | {wrap(p["C"])} | {wrap(p["D"])}')],
    'or4b_2':    lambda p: [('X', f'{wrap(p["A"])} | {wrap(p["B"])} | {wrap(p["C"])} | ~{wrap(p["D_N"])}')],
    'or4bb_2':   lambda p: [('X', f'{wrap(p["A"])} | {wrap(p["B"])} | ~{wrap(p["C_N"])} | ~{wrap(p["D_N"])}')],

    # NOR family
    'nor2_2':    lambda p: [('Y', f'~({wrap(p["A"])} | {wrap(p["B"])})')],
    'nor3_2':    lambda p: [('Y', f'~({wrap(p["A"])} | {wrap(p["B"])} | {wrap(p["C"])})')],
    'nor3b_2':   lambda p: [('Y', f'~({wrap(p["A"])} | {wrap(p["B"])} | ~{wrap(p["C_N"])})')],
    'nor4_2':    lambda p: [('Y', f'~({wrap(p["A"])} | {wrap(p["B"])} | {wrap(p["C"])} | {wrap(p["D"])})')],
    'nor4b_2':   lambda p: [('Y', f'~({wrap(p["A"])} | {wrap(p["B"])} | {wrap(p["C"])} | ~{wrap(p["D_N"])})')],

    # XOR / XNOR  (NOTE: xnor2_2 output port is Y in Sky130 hd, not X)
    'xor2_2':    lambda p: [('X', f'{wrap(p["A"])} ^ {wrap(p["B"])}')],
    'xnor2_2':   lambda p: [('Y', f'~({wrap(p["A"])} ^ {wrap(p["B"])})')],

    # Mux  (NOTE: Sky130 mux2_1 uses A0/A1, not A/B)
    'mux2_1':    lambda p: [('X', f'({wrap(p["S"])} ? {wrap(p["A1"])} : {wrap(p["A0"])})')],

    # AND-OR complex cells
    'a21o_2':    lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])}) | {wrap(p["B1"])}')],
    'a21oi_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])}) | {wrap(p["B1"])})')],
    'a21bo_2':   lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])}) | ~{wrap(p["B1_N"])}')],
    'a21boi_2':  lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])}) | ~{wrap(p["B1_N"])})')],
    'a22o_2':    lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])}) | ({wrap(p["B1"])} & {wrap(p["B2"])})')],
    'a22oi_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])}) | ({wrap(p["B1"])} & {wrap(p["B2"])}))')],
    'a221o_2':   lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])}) | ({wrap(p["B1"])} & {wrap(p["B2"])}) | {wrap(p["C1"])}')],
    'a221oi_2':  lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])}) | ({wrap(p["B1"])} & {wrap(p["B2"])}) | {wrap(p["C1"])})')],
    'a211o_2':   lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])}) | {wrap(p["B1"])} | {wrap(p["C1"])}')],
    'a211oi_2':  lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])}) | {wrap(p["B1"])} | {wrap(p["C1"])})')],
    'a2111oi_2': lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])}) | {wrap(p["B1"])} | {wrap(p["C1"])} | {wrap(p["D1"])})')],
    'a311o_2':   lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])} & {wrap(p["A3"])}) | {wrap(p["B1"])} | {wrap(p["C1"])}')],
    'a31o_2':    lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])} & {wrap(p["A3"])}) | {wrap(p["B1"])}')],
    'a31oi_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])} & {wrap(p["A3"])}) | {wrap(p["B1"])})')],
    'a32o_2':    lambda p: [('X', f'({wrap(p["A1"])} & {wrap(p["A2"])} & {wrap(p["A3"])}) | ({wrap(p["B1"])} & {wrap(p["B2"])})')],
    'a41oi_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} & {wrap(p["A2"])} & {wrap(p["A3"])} & {wrap(p["A4"])}) | {wrap(p["B1"])})')],

    # OR-AND complex cells
    'o21a_2':    lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])}) & {wrap(p["B1"])}')],
    'o21ai_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} | {wrap(p["A2"])}) & {wrap(p["B1"])})')],
    'o21ba_2':   lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])}) & ~{wrap(p["B1_N"])}')],
    'o21bai_2':  lambda p: [('Y', f'~(({wrap(p["A1"])} | {wrap(p["A2"])}) & ~{wrap(p["B1_N"])})')],
    'o22a_2':    lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])}) & ({wrap(p["B1"])} | {wrap(p["B2"])})')],
    'o22ai_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} | {wrap(p["A2"])}) & ({wrap(p["B1"])} | {wrap(p["B2"])}))')],
    'o211a_2':   lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])}) & {wrap(p["B1"])} & {wrap(p["C1"])}')],
    'o211ai_2':  lambda p: [('Y', f'~(({wrap(p["A1"])} | {wrap(p["A2"])}) & {wrap(p["B1"])} & {wrap(p["C1"])})')],
    'o221a_2':   lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])}) & ({wrap(p["B1"])} | {wrap(p["B2"])}) & {wrap(p["C1"])}')],
    'o2bb2a_2':  lambda p: [('X', f'(~{wrap(p["A1_N"])} | ~{wrap(p["A2_N"])}) & ({wrap(p["B1"])} | {wrap(p["B2"])})')],
    'o311a_2':   lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])} | {wrap(p["A3"])}) & {wrap(p["B1"])} & {wrap(p["C1"])}')],
    'o31a_2':    lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])} | {wrap(p["A3"])}) & {wrap(p["B1"])}')],
    'o31ai_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} | {wrap(p["A2"])} | {wrap(p["A3"])}) & {wrap(p["B1"])})')],
    'o32a_2':    lambda p: [('X', f'({wrap(p["A1"])} | {wrap(p["A2"])} | {wrap(p["A3"])}) & ({wrap(p["B1"])} | {wrap(p["B2"])})')],
    'o32ai_2':   lambda p: [('Y', f'~(({wrap(p["A1"])} | {wrap(p["A2"])} | {wrap(p["A3"])}) & ({wrap(p["B1"])} | {wrap(p["B2"])}))')],

    # Constant tie
    'conb_1':    lambda p: [('HI', '1'), ('LO', '0')],

    # Flip-flops: Q is an opaque state variable named Q_<net>
    'dfrtp_2':   lambda p: [('Q', f'Q_{p["_Q_NET"]}')],
    'dfstp_2':   lambda p: [('Q', f'Q_{p["_Q_NET"]}')],
    'dfxtp_2':   lambda p: [('Q', f'Q_{p["_Q_NET"]}')],
}

# Output port name for each cell type (determined from actual Sky130 hd netlists)
OUTPUT_PORT = {
    'inv_2': 'Y', 'buf_2': 'X', 'clkbuf_16': 'X', 'clkbuf_8': 'X',
    'and2_2': 'X', 'and2b_2': 'X', 'and3_2': 'X', 'and3b_2': 'X',
    'and4_2': 'X', 'and4b_2': 'X', 'and4bb_2': 'X',
    'nand2_2': 'Y', 'nand2b_2': 'Y', 'nand3_2': 'Y', 'nand3b_2': 'Y', 'nand4_2': 'Y',
    'or2_2': 'X', 'or3_2': 'X', 'or3b_2': 'X',
    'or4_2': 'X', 'or4b_2': 'X', 'or4bb_2': 'X',
    'nor2_2': 'Y', 'nor3_2': 'Y', 'nor3b_2': 'Y', 'nor4_2': 'Y', 'nor4b_2': 'Y',
    'xor2_2': 'X', 'xnor2_2': 'Y',   # xnor2_2 uses Y !
    'mux2_1': 'X',
    'a21o_2': 'X', 'a21oi_2': 'Y', 'a21bo_2': 'X', 'a21boi_2': 'Y',
    'a22o_2': 'X', 'a22oi_2': 'Y',
    'a221o_2': 'X', 'a221oi_2': 'Y',
    'a211o_2': 'X', 'a211oi_2': 'Y',
    'a2111oi_2': 'Y', 'a311o_2': 'X', 'a31o_2': 'X', 'a31oi_2': 'Y',
    'a32o_2': 'X', 'a41oi_2': 'Y',
    'o21a_2': 'X', 'o21ai_2': 'Y', 'o21ba_2': 'X', 'o21bai_2': 'Y',
    'o22a_2': 'X', 'o22ai_2': 'Y',
    'o211a_2': 'X', 'o211ai_2': 'Y',
    'o221a_2': 'X', 'o2bb2a_2': 'X',
    'o311a_2': 'X', 'o31a_2': 'X', 'o31ai_2': 'Y',
    'o32a_2': 'X', 'o32ai_2': 'Y',
}

FF_TYPES = {'dfrtp_2', 'dfstp_2', 'dfxtp_2'}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_netlist(path):
    with open(path) as f:
        text = f.read()

    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//.*', '', text)

    module_ports = {}
    for m in re.finditer(r'\b(input|output)\s+(\w+)\s*;', text):
        module_ports[m.group(2)] = m.group(1)

    cells = []
    skip_kw = {'module', 'endmodule', 'input', 'output', 'wire', 'reg',
               'assign', 'always', 'initial', 'begin', 'end', 'integer'}
    inst_re = re.compile(r'(\w+)\s+(\w+)\s*\(([^;]+?)\)\s*;', re.DOTALL)
    port_re = re.compile(r'\.\s*(\w+)\s*\(\s*(\w+)\s*\)')

    for m in inst_re.finditer(text):
        cell_type, inst_name, port_block = m.group(1), m.group(2), m.group(3)
        if cell_type in skip_kw:
            continue
        ports = {pm.group(1): pm.group(2) for pm in port_re.finditer(port_block)}
        cells.append((cell_type, inst_name, ports))

    return module_ports, cells


# ---------------------------------------------------------------------------
# Build symbolic expressions
# ---------------------------------------------------------------------------

def build_expressions(module_ports, cells):
    # Seed primary inputs
    expr = {}
    for name, direction in module_ports.items():
        if direction == 'input':
            expr[name] = name

    # Seed conb_1 constants first (they have no inputs to resolve)
    for cell_type, inst_name, ports in cells:
        if cell_type == 'conb_1':
            for pname, net in ports.items():
                if pname == 'HI':
                    expr[net] = '1'
                elif pname == 'LO':
                    expr[net] = '0'

    # Seed FF Q outputs as opaque state variables, collect FF metadata
    ff_info = {}
    for cell_type, inst_name, ports in cells:
        if cell_type in FF_TYPES:
            q_net = ports.get('Q')
            if q_net:
                expr[q_net] = f'Q_{q_net}'
                ff_info[q_net] = {
                    'D': ports.get('D'),
                    'CLK': ports.get('CLK'),
                    'type': cell_type,
                    'inst': inst_name,
                }

    # Build set of all nets that need to be computed (output nets of comb cells)
    # and a lookup: output_net -> (cell_type, inst_name, ports)
    net_to_cell = {}
    for cell_type, inst_name, ports in cells:
        if cell_type in FF_TYPES or cell_type == 'conb_1':
            continue
        op = OUTPUT_PORT.get(cell_type)
        if op and op in ports:
            out_net = ports[op]
            net_to_cell[out_net] = (cell_type, inst_name, ports)

    # Identify undriven wires (inputs with no driver)
    all_input_nets = set()
    for cell_type, inst_name, ports in cells:
        op = OUTPUT_PORT.get(cell_type, None)
        ff_out = {'Q', 'HI', 'LO'}
        for pname, net in ports.items():
            if pname not in (({op} if op else set()) | ff_out):
                all_input_nets.add(net)

    driven_nets = set(expr.keys()) | set(net_to_cell.keys())
    undriven = all_input_nets - driven_nets
    if undriven:
        print(f'[!] Undriven wire(s) (treated as undefined): {sorted(undriven)}',
              file=sys.stderr)
        for net in undriven:
            expr[net] = f'UNDEF_{net}'

    # Iterative fixpoint propagation
    pending = set(net_to_cell.keys()) - set(expr.keys())

    max_iters = 1000
    for iteration in range(max_iters):
        if not pending:
            print(f'[*] Fully resolved after {iteration + 1} iteration(s).')
            break

        newly_resolved = []
        for out_net in list(pending):
            cell_type, inst_name, ports = net_to_cell[out_net]
            op = OUTPUT_PORT[cell_type]

            # Try to resolve all input ports
            resolved = {}
            all_ok = True
            for pname, net in ports.items():
                if pname == op:
                    continue
                if net in expr:
                    resolved[pname] = expr[net]
                else:
                    all_ok = False
                    break

            if all_ok:
                fn = CELL_DEFS.get(cell_type)
                if fn:
                    out_pairs = fn(resolved)
                    for out_port, out_expr in out_pairs:
                        if ports.get(out_port) == out_net:
                            expr[out_net] = out_expr
                            newly_resolved.append(out_net)
                            break

        for net in newly_resolved:
            pending.discard(net)

        if not newly_resolved and pending:
            print(f'[!] Stuck at iteration {iteration + 1}: {len(pending)} nets unresolvable.',
                  file=sys.stderr)
            for net in sorted(pending)[:5]:
                ct, inst, ports = net_to_cell[net]
                op = OUTPUT_PORT[ct]
                missing = [f'{pn}={pv}' for pn, pv in ports.items()
                           if pn != op and pv not in expr]
                print(f'    {ct} {inst} -> {net}: missing {missing}', file=sys.stderr)
            break
    else:
        if pending:
            print(f'[!] Did not converge after {max_iters} iterations, {len(pending)} nets remain.',
                  file=sys.stderr)

    return expr, ff_info, pending


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('netlist', nargs='?', default='resynth_cleaned.v')
    ap.add_argument('--output', '-o', default='bool_exprs.txt')
    args = ap.parse_args()

    print(f'[*] Parsing {args.netlist} ...')
    module_ports, cells = parse_netlist(args.netlist)
    print(f'[*] Total cells: {len(cells)}')
    print(f'[*] Inputs:  {sorted(n for n, d in module_ports.items() if d == "input")}')
    print(f'[*] Outputs: {sorted(n for n, d in module_ports.items() if d == "output")}')

    print(f'[*] Building symbolic expressions...')
    expr, ff_info, unresolved_nets = build_expressions(module_ports, cells)
    print(f'[*] Total nets resolved: {len(expr)}')

    primary_outputs = sorted(n for n, d in module_ports.items() if d == 'output')

    SEP = '=' * 80

    with open(args.output, 'w') as f:
        f.write(f'{SEP}\n')
        f.write('PRIMARY OUTPUT BOOLEAN EXPRESSIONS\n')
        f.write('  Q_<net> = current state of flip-flop\n')
        f.write('  Primary inputs: I, clk, enable, rst_n\n')
        f.write(f'{SEP}\n\n')

        for out in primary_outputs:
            e = expr.get(out, f'<UNRESOLVED: {out}>')
            f.write(f'{out} =\n  {e}\n\n')

        f.write(f'\n{SEP}\n')
        f.write('FLIP-FLOP NEXT-STATE EQUATIONS\n')
        f.write('  On rising CLK edge: Q_<net> becomes D\n')
        f.write(f'{SEP}\n\n')

        for q_net in sorted(ff_info.keys()):
            info = ff_info[q_net]
            d_net = info['D']
            clk_net = info['CLK']
            d_expr = expr.get(d_net, f'<UNRESOLVED: {d_net}>')
            clk_expr = expr.get(clk_net, f'<UNRESOLVED: {clk_net}>')
            f.write(f'[ {info["type"]} : {info["inst"]} ]\n')
            f.write(f'  State var  : Q_{q_net}\n')
            f.write(f'  CLK        : {clk_expr}\n')
            f.write(f'  D (next)   : {d_expr}\n\n')

        if unresolved_nets:
            f.write(f'\n{SEP}\n')
            f.write(f'UNRESOLVABLE NETS ({len(unresolved_nets)})\n')
            f.write(f'{SEP}\n\n')
            for net in sorted(unresolved_nets):
                f.write(f'{net}\n')

        f.write(f'\n{SEP}\n')
        f.write('ALL NET EXPRESSIONS\n')
        f.write(f'{SEP}\n\n')
        for net, e in sorted(expr.items()):
            f.write(f'{net} = {e}\n')

    print(f'[*] Results written to: {args.output}')

    print(f'\n{"=" * 60}')
    print('PRIMARY OUTPUTS:')
    print('=' * 60)
    for out in primary_outputs:
        e = expr.get(out, '<UNRESOLVED>')
        if len(e) > 140:
            short_e = e[:140] + f'  ...  [see {args.output} for full]'
        else:
            short_e = e
        print(f'\n{out} =\n  {short_e}')

    print(f'\n{"=" * 60}')
    print(f'Flip-flops: {len(ff_info)}')
    print(f'State variables: {sorted("Q_" + q for q in ff_info.keys())}')


if __name__ == '__main__':
    main()
