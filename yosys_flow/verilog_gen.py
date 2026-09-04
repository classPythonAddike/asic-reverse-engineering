import sys
import os
import re

def parse_expressions(file_content):
    """
    Parses logic equations for primary outputs and flip-flops with resilient matching.
    """
    primary_outputs = {}
    flip_flops = {}
    
    # Split on any line containing 3 or more '=' characters
    sections = re.split(r'=3,', file_content)
    
    # If no '=' delimiters exist, evaluate the entire content as one block
    if len(sections) == 1:
        sections = [file_content]
    
    for section in sections:
        section_upper = section.upper()
        
        # Primary Outputs Parsing
        if 'PRIMARY OUTPUT' in section_upper or 'OUTPUT' in section_upper:
            # Matches: Var = Expression (flexible with spaces/newlines)
            matches = re.findall(r'([A-Za-z_]\w*)\s*=\s*([^=\n]+)', section)
            for var_name, expr in matches:
                expr_cleaned = " ".join(expr.strip().split())
                if var_name.strip() and expr_cleaned:
                    primary_outputs[var_name.strip()] = expr_cleaned
                    
        # Flip-Flop Equations Parsing
        if 'FLIP-FLOP' in section_upper or 'NEXT-STATE' in section_upper or 'STATE' in section_upper:
            # Matches flexible patterns like "State var : Q0" and "D (next) : expr" or "D : expr"
            ff_blocks = re.findall(
                r'State\s*var\s*:\s*(\w+)[\s\S]*?D\s*(?:\(next\))?\s*:\s*([^\n\r]+)', 
                section, 
                re.IGNORECASE
            )
            for var_name, d_expr in ff_blocks:
                expr_cleaned = " ".join(d_expr.strip().split())
                if var_name.strip() and expr_cleaned:
                    flip_flops[var_name.strip()] = expr_cleaned
                    
    return primary_outputs, flip_flops

def convert_to_verilog(expr):
    """
    Converts Boolean logic expressions into valid Verilog operators.
    """
    return expr.strip()

def extract_variables(expressions):
    """
    Extracts all state/input variables present in the logic expressions.
    """
    variables = set()
    for expr in expressions:
        tokens = re.findall(r'\b[A-Za-z_]\w*\b', expr)
        for token in tokens:
            if token not in {'0', '1', 'clk', 'rst_n', 'enable', 'I'}:
                variables.add(token)
    return variables

def is_target_output(var_name):
    """
    Checks if a variable name matches specified output patterns:
    O_<number>, _I<number>, or success.
    """
    return bool(re.match(r'^(O_\d+|_I\d+|success)$', var_name))

def generate_verilog_code(primary_outputs, flip_flops, module_name="logic_module"):
    """
    Generates structured Verilog HDL code with restricted output declarations.
    """
    if not primary_outputs and not flip_flops:
        raise ValueError("No Boolean expressions or flip-flops were successfully parsed.")

    # Filter primary outputs to keep only requested target signals
    filtered_outputs = {
        k: v for k, v in primary_outputs.items() if is_target_output(k)
    }

    all_exprs = list(primary_outputs.values()) + list(flip_flops.values())
    all_vars = extract_variables(all_exprs)
    
    out_ports = sorted(filtered_outputs.keys())
    ff_vars = sorted(flip_flops.keys())
    all_ff_and_state = sorted(all_vars.union(ff_vars))

    lines = [
        f"module {module_name} (",
        "    input wire clk,",
        "    input wire rst_n,",
        "    input wire enable,",
        "    input wire I"
    ]
    
    # Declare only specified outputs
    for out in out_ports:
        lines.append(f",\n    output wire {out}")
        
    lines.append("\n);")
    lines.append("")
    
    lines.append("    // Flip-flop state variables")
    for var in all_ff_and_state:
        lines.append(f"    reg {var};")
    lines.append("")
    
    lines.append("    // Next-state signals for flip-flops")
    for var in ff_vars:
        lines.append(f"    wire {var}_next;")
    lines.append("")
    
    lines.append("    // Flip-flop next-state logic assignments")
    for var, expr in flip_flops.items():
        lines.append(f"    assign {var}_next = {convert_to_verilog(expr)};")
    lines.append("")
    
    lines.append("    // Sequential state update on clock edge")
    lines.append("    always @(posedge clk or negedge rst_n) begin")
    lines.append("        if (!rst_n) begin")
    for var in all_ff_and_state:
        lines.append(f"            {var} <= 1'b0;")
    lines.append("        end else if (enable) begin")
    for var in ff_vars:
        lines.append(f"            {var} <= {var}_next;")
    lines.append("        end")
    lines.append("    end")
    lines.append("")
    
    lines.append("    // Target primary output logic assignments")
    for out, expr in filtered_outputs.items():
        lines.append(f"    assign {out} = {convert_to_verilog(expr)};")
    lines.append("")
    
    lines.append("endmodule")
    return "\n".join(lines)
def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "bool_exprs.txt"
    
    if not os.path.exists(input_file):
        print(f"Error: Target input file '{input_file}' could not be opened or found.")
        print("Please verify the file path or supply it as a command argument: python script.py <filename>")
        sys.exit(1)
        
    with open(input_file, 'r') as f:
        content = f.read()
        
    try:
        primary_outputs, flip_flops = parse_expressions(content)
        verilog_code = generate_verilog_code(primary_outputs, flip_flops)
        
        output_file = "generated_module.v"
        with open(output_file, 'w') as f:
            f.write(verilog_code)
            
        print(f"Successfully generated Verilog module in '{output_file}'.")
    except Exception as err:
        print(f"Failed to generate Verilog module: {err}")

if __name__ == "__main__":
    main()
