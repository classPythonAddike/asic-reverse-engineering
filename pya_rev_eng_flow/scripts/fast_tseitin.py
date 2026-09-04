import z3
import re
import sys

def tokenize(expr):
    tokens = []
    i = 0
    n = len(expr)
    while i < n:
        if expr[i].isspace():
            i += 1
        elif expr[i] in '()~&|^':
            tokens.append(expr[i])
            i += 1
        elif expr[i] == '?':
            tokens.append('?')
            i += 1
        elif expr[i] == ':':
            tokens.append(':')
            i += 1
        else:
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == '_'):
                j += 1
            if i == j:
                raise ValueError("Unexpected char")
            tokens.append(expr[i:j])
            i = j
    return tokens

class ASTNode:
    def __init__(self, op, children, key):
        self.op = op
        self.children = children
        self.key = key
        self.id = -1 # to be assigned later

global_cache = {}

def create_node(op, children):
    if op == 'var':
        key = f"var_{children[0]}"
    elif op == '~':
        key = f"~_{children[0].key}"
    elif op == 'ite':
        key = f"ite_{children[0].key}_{children[1].key}_{children[2].key}"
    else:
        # commutative
        c1, c2 = children[0].key, children[1].key
        if c1 > c2: c1, c2 = c2, c1
        key = f"{op}_{c1}_{c2}"
        
    if key in global_cache:
        return global_cache[key]
        
    node = ASTNode(op, children, key)
    global_cache[key] = node
    return node

def parse_to_dag(tokens):
    precedence = {'~': 5, '&': 4, '^': 3, '|': 2, '?': 1, ':': 1, '(': 0}
    out = []
    ops = []
    
    def apply_op():
        op = ops.pop()
        if op == '~':
            a = out.pop()
            out.append(create_node('~', [a]))
        elif op in ['&', '|', '^']:
            b = out.pop()
            a = out.pop()
            out.append(create_node(op, [a, b]))
        elif op == '?':
            pass 
        elif op == ':':
            c = out.pop()
            b = out.pop()
            a = out.pop()
            out.append(create_node('ite', [a, b, c]))

    for token in tokens:
        if token == '(':
            ops.append(token)
        elif token == ')':
            while ops and ops[-1] != '(':
                apply_op()
            ops.pop()
        elif token in precedence:
            while ops and precedence[ops[-1]] >= precedence[token]:
                if token == '~' and ops[-1] == '~': break 
                if token in ['?', ':'] and ops[-1] in ['?', ':']: break 
                if token == ':' and ops[-1] == '?': break 
                apply_op()
            ops.append(token)
        else:
            out.append(create_node('var', [token]))
            
    while ops:
        apply_op()
        
    return out[0]

def main():
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bool_exprs_path = os.path.join(script_dir, 'bool_exprs.txt')
    solution_path = os.path.join(script_dir, 'solution.txt')
    print(f"Parsing {bool_exprs_path}...")
    with open(bool_exprs_path, 'r') as f:
        content = f.read()

    po_section = content.split('PRIMARY OUTPUT BOOLEAN EXPRESSIONS')[1].split('FLIP-FLOP NEXT-STATE EQUATIONS')[0]
    outputs = {}
    for m in re.finditer(r'^(\w+)\s*=\s*\n\s*(.+?)\n\n', po_section, re.MULTILINE | re.DOTALL):
        outputs[m.group(1)] = m.group(2).strip()

    ff_section = content.split('FLIP-FLOP NEXT-STATE EQUATIONS')[1].split('UNRESOLVABLE NETS')[0]
    if 'ALL NET EXPRESSIONS' in ff_section:
        ff_section = ff_section.split('ALL NET EXPRESSIONS')[0]
        
    ffs = {}
    for block in ff_section.split('['):
        q_m = re.search(r'State var\s*:\s*(Q_\w+)', block)
        d_m = re.search(r'D \(next\)\s*:\s*(.+)', block)
        if q_m and d_m: ffs[q_m.group(1)] = d_m.group(1).strip()

    # Build Global DAG
    print("Building Global DAG...")
    ff_dag_roots = {}
    for name, expr in ffs.items():
        ff_dag_roots[name] = parse_to_dag(tokenize(expr))
        
    success_root = parse_to_dag(tokenize(outputs['success']))
    
    # Collect all unique nodes (topological sort naturally by extracting from global_cache values)
    # Wait, global_cache insertion order IS a valid topological order because a node is created only after its children!
    # Let's filter out only internal nodes (not 'var')
    internal_nodes = []
    node_id_counter = 0
    for key, node in global_cache.items():
        if node.op != 'var':
            node.id = node_id_counter
            internal_nodes.append(node)
            node_id_counter += 1
            
    print(f"Total unique internal gates in DAG: {len(internal_nodes)}")

    solver = z3.Solver()
    
    z3_vars = {}
    
    def get_var(name, cycle):
        if name == '0':
            return z3.BoolVal(False)
        elif name == '1':
            return z3.BoolVal(True)
        elif name in ['I', 'enable', 'rst_n', 'clk']:
            var_name = f"{name}_{cycle}"
        elif name.startswith('UNDEF__'):
            return z3.BoolVal(False)
        else:
            var_name = f"{name}_{cycle - 1}"
            
        if var_name not in z3_vars:
            z3_vars[var_name] = z3.Bool(var_name)
        return z3_vars[var_name]
        
    # Initial state
    for name in ffs:
        z3_vars[f"{name}_0"] = z3.Bool(f"{name}_0")
        solver.add(z3_vars[f"{name}_0"] == False)
        
    MAX_CYCLES = 300
    print(f"Unrolling up to {MAX_CYCLES} cycles...")
    
    for cycle in range(1, MAX_CYCLES + 1):
        # inputs
        z3_vars[f"enable_{cycle}"] = z3.Bool(f"enable_{cycle}")
        z3_vars[f"rst_n_{cycle}"] = z3.Bool(f"rst_n_{cycle}")
        solver.add(z3_vars[f"enable_{cycle}"] == True)
        solver.add(z3_vars[f"rst_n_{cycle}"] == True)
        
        node_z3_vars = {}
        
        def resolve_child(child):
            if child.op == 'var':
                return get_var(child.children[0], cycle)
            else:
                return node_z3_vars[child.id]
                
        # Topologically instantiate gates for this cycle
        for node in internal_nodes:
            v = z3.Bool(f"n_{node.id}_c_{cycle}")
            node_z3_vars[node.id] = v
            if node.op == '~':
                a = resolve_child(node.children[0])
                solver.add(v == z3.Not(a))
            elif node.op == '&':
                a, b = resolve_child(node.children[0]), resolve_child(node.children[1])
                solver.add(v == z3.And(a, b))
            elif node.op == '|':
                a, b = resolve_child(node.children[0]), resolve_child(node.children[1])
                solver.add(v == z3.Or(a, b))
            elif node.op == '^':
                a, b = resolve_child(node.children[0]), resolve_child(node.children[1])
                solver.add(v == z3.Xor(a, b))
            elif node.op == 'ite':
                a, b, c = resolve_child(node.children[0]), resolve_child(node.children[1]), resolve_child(node.children[2])
                solver.add(v == z3.If(a, b, c))
                
        # Link next states
        for name, root in ff_dag_roots.items():
            next_state_var = z3.Bool(f"{name}_{cycle}")
            z3_vars[f"{name}_{cycle}"] = next_state_var
            root_z3 = resolve_child(root)
            solver.add(next_state_var == root_z3)
            
        # check success
        success_z3 = resolve_child(success_root)
        solver.push()
        solver.add(success_z3 == True)
        
        print(f"Checking SAT for cycle {cycle}...")
        if solver.check() == z3.sat:
            print(f"\nWIN! Puzzle solved at cycle {cycle}!")
            model = solver.model()
            seq = []
            for i in range(1, cycle + 1):
                i_var = z3_vars[f"I_{i}"]
                val = model.eval(i_var, model_completion=True)
                seq.append('1' if z3.is_true(val) else '0')
            seq_str = "".join(seq)
            print("Input sequence: " + seq_str)
            with open(solution_path, 'w') as f:
                f.write(seq_str)
            break
        else:
            solver.pop()

if __name__ == '__main__':
    main()
