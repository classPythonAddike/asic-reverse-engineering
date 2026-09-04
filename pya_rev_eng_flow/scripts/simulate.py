#!/usr/bin/env python3
"""
Python simulator for puzzle_fixed - reads bool_exprs.txt and solution.txt
from the same directory, runs the simulation, and reports results.
"""
import re
import os
import json

script_dir = os.path.dirname(os.path.abspath(__file__))

def tokenize(expr):
    tokens = []
    i, n = 0, len(expr)
    while i < n:
        if expr[i].isspace(): i += 1
        elif expr[i] in '()~&|^':
            tokens.append(expr[i]); i += 1
        elif expr[i] == '?':
            tokens.append('?'); i += 1
        elif expr[i] == ':':
            tokens.append(':'); i += 1
        else:
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == '_'): j += 1
            tokens.append(expr[i:j]); i = j
    return tokens

class ASTNode:
    def __init__(self, op, children, key):
        self.op = op; self.children = children; self.key = key; self.id = -1

global_cache = {}

def create_node(op, children):
    if op == 'var': key = f"var_{children[0]}"
    elif op == '~': key = f"~_{children[0].key}"
    elif op == 'ite': key = f"ite_{children[0].key}_{children[1].key}_{children[2].key}"
    else:
        c1, c2 = children[0].key, children[1].key
        if c1 > c2: c1, c2 = c2, c1
        key = f"{op}_{c1}_{c2}"
    if key in global_cache: return global_cache[key]
    node = ASTNode(op, children, key)
    global_cache[key] = node
    return node

def parse_to_dag(tokens):
    precedence = {'~': 5, '&': 4, '^': 3, '|': 2, '?': 1, ':': 1, '(': 0}
    out, ops = [], []
    def apply_op():
        op = ops.pop()
        if op == '~': out.append(create_node('~', [out.pop()]))
        elif op in ['&', '|', '^']:
            b, a = out.pop(), out.pop()
            out.append(create_node(op, [a, b]))
        elif op == '?': pass
        elif op == ':':
            c, b, a = out.pop(), out.pop(), out.pop()
            out.append(create_node('ite', [a, b, c]))
    for token in tokens:
        if token == '(': ops.append(token)
        elif token == ')':
            while ops and ops[-1] != '(': apply_op()
            ops.pop()
        elif token in precedence:
            while ops and precedence.get(ops[-1], -1) >= precedence[token]:
                if token == '~' and ops[-1] == '~': break
                if token in ['?', ':'] and ops[-1] in ['?', ':']: break
                if token == ':' and ops[-1] == '?': break
                apply_op()
            ops.append(token)
        else: out.append(create_node('var', [token]))
    while ops: apply_op()
    return out[0]

def main():
    with open(os.path.join(script_dir, 'bool_exprs.txt'), 'r') as f:
        content = f.read()

    # Parse outputs
    po_section = content.split('PRIMARY OUTPUT BOOLEAN EXPRESSIONS')[1].split('FLIP-FLOP NEXT-STATE EQUATIONS')[0]
    outputs = {}
    for m in re.finditer(r'^(\w+)\s*=\n\s*(.+?)\n\n', po_section, re.MULTILINE | re.DOTALL):
        outputs[m.group(1)] = m.group(2).strip()

    # Parse FFs
    ff_section = content.split('FLIP-FLOP NEXT-STATE EQUATIONS')[1].split('UNRESOLVABLE NETS')[0]
    if 'ALL NET EXPRESSIONS' in ff_section: ff_section = ff_section.split('ALL NET EXPRESSIONS')[0]
    ffs = {}
    for block in ff_section.split('['):
        q_m = re.search(r'State var\s*:\s*(Q_\w+)', block)
        d_m = re.search(r'D \(next\)\s*:\s*(.+)', block)
        if q_m and d_m: ffs[q_m.group(1)] = d_m.group(1).strip()

    ff_dag_roots = {name: parse_to_dag(tokenize(expr)) for name, expr in ffs.items()}
    out_dag_roots = {name: parse_to_dag(tokenize(expr)) for name, expr in outputs.items()}

    internal_nodes = []
    nid = 0
    for node in global_cache.values():
        if node.op != 'var':
            node.id = nid; internal_nodes.append(node); nid += 1

    with open(os.path.join(script_dir, 'solution.txt'), 'r') as f:
        seq = f.read().strip()

    state = {name: False for name in ffs}

    def get_var(name, inputs):
        if name == '0': return False
        if name == '1': return True
        if name in inputs: return inputs[name]
        if name.startswith('UNDEF__'): return False
        return state.get(name, False)

    trace = []
    for i, bit in enumerate(seq):
        inputs = {'I': bit == '1', 'enable': True, 'rst_n': True, 'clk': False}
        node_vals = {}

        def resolve(child):
            if child.op == 'var': return get_var(child.children[0], inputs)
            return node_vals[child.id]

        for node in internal_nodes:
            if node.op == '~': v = not resolve(node.children[0])
            elif node.op == '&': v = resolve(node.children[0]) and resolve(node.children[1])
            elif node.op == '|': v = resolve(node.children[0]) or resolve(node.children[1])
            elif node.op == '^': v = resolve(node.children[0]) ^ resolve(node.children[1])
            elif node.op == 'ite': v = resolve(node.children[1]) if resolve(node.children[0]) else resolve(node.children[2])
            node_vals[node.id] = v

        success_val = resolve(out_dag_roots['success'])
        out_bits = []
        for bit_idx in range(8):
            out_name = f'O_{bit_idx}_'
            if out_name in out_dag_roots:
                out_bits.append('1' if resolve(out_dag_roots[out_name]) else '0')
            else:
                out_bits.append('0')

        char_val = int("".join(reversed(out_bits)), 2)
        char_str = chr(char_val) if 32 <= char_val <= 126 else '?'
        print(f"Cycle {i+1:3d} (I={bit}) -> success={int(success_val)}, O_7..O_0={''.join(reversed(out_bits))} ('{char_str}')")

        cycle_entry = {
            "Cycle": i + 1, "Input_I": int(bit), "success": bool(success_val),
            "O_7_to_O_0": "".join(reversed(out_bits)), "ASCII": char_str,
            "FF_State": {k: int(v) for k, v in state.items()}
        }
        trace.append(cycle_entry)

        next_state = {name: resolve(root) for name, root in ff_dag_roots.items()}
        state = next_state

    # Write light trace
    with open(os.path.join(script_dir, 'light_trace.json'), 'w') as f:
        json.dump(trace, f, indent=2)
    print(f"\nTrace saved to puzzle_fixed/light_trace.json")

    final = trace[-1]
    print(f"\n=== FINAL RESULT ===")
    print(f"Sequence length: {len(seq)} bits")
    print(f"SUCCESS at cycle {len(seq)}: {final['success']}")
    print(f"Output O_7..O_0: {final['O_7_to_O_0']} = {int(final['O_7_to_O_0'],2)} decimal = '{final['ASCII']}'")

if __name__ == '__main__':
    main()
