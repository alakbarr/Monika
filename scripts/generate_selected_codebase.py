import os
import ast

def strip_python_comments_and_docstrings(source_code):
    try:
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if ast.get_docstring(node):
                    node.body.pop(0)
        return ast.unparse(tree)
    except Exception as e:
        print(f"  -> Note: AST parse failed (SyntaxError), keeping original code.")
        return source_code

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    structure_path = os.path.join(root_dir, "selected_structure.md")
    with open(structure_path, 'r', encoding='utf-8') as f:
        tree_str = f.read()

    output_path = os.path.join(root_dir, "selected_codebase.md")
    
    lines = tree_str.split("\n")
    filepaths = []
    current_path = []

    for line in lines:
        line_clean = line.rstrip('\n')
        if not line_clean:
            continue
            
        if line_clean in ("ClaudeTrade/", "AITrade/", "TradingAgent/", f"{os.path.basename(root_dir)}/"):
            continue
            
        prefix_idx = max(line_clean.find("├──"), line_clean.find("└──"))
        if prefix_idx != -1:
            depth = prefix_idx // 4
            name = line_clean[prefix_idx + 4:].strip()
            
            if name.endswith('/'):
                name = name[:-1]
                
            current_path = current_path[:depth]
            current_path.append(name)
            
            if any(name.endswith(ext) for ext in [".py", ".mq5", ".yaml", ".md", ".bat"]):
                full_path = os.path.join(root_dir, *current_path)
                filepaths.append(full_path)

    with open(output_path, 'w', encoding='utf-8') as out_f:
        out_f.write("# Selected Codebase\n\n")
        out_f.write("This file contains the complete source code for the specified files.\n\n")
        out_f.write("## Directory Structure\n\n```text\n")
        out_f.write(tree_str)
        out_f.write("\n```\n\n")
        
        for fp in filepaths:
            if not os.path.exists(fp):
                print(f"Warning: File not found: {fp}")
                continue
                
            print(f"Adding {fp}")
            ext = os.path.splitext(fp)[1][1:]
            
            lang = ext
            if ext == "mq5":
                lang = "cpp"
            
            out_f.write(f"## {os.path.relpath(fp, start=root_dir)}\n\n")
            out_f.write(f"```{lang}\n")
            try:
                with open(fp, 'r', encoding='utf-8') as in_f:
                    content = in_f.read()
                    
                if ext == "py":
                    content = strip_python_comments_and_docstrings(content)
                    
                out_f.write(content)
            except Exception as e:
                out_f.write(f"// Error reading file: {e}\n")
            out_f.write(f"\n```\n\n")
            
    print(f"Codebase written to {output_path}")

if __name__ == "__main__":
    main()
