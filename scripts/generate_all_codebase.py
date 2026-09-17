import os
import re
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
    struktur_path = os.path.join(root_dir, "STRUKTUR.md")
    output_path = os.path.join(root_dir, "all_codebase.md")
    
    with open(struktur_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    filepaths = []
    current_path = []

    # Priority files at the very top
    priority_files = [
        os.path.join(root_dir, "STRUKTUR.md"),
        os.path.join(root_dir, "INDEX.md"),
        os.path.join(root_dir, "trading-agent", "main.py"),
        os.path.join(root_dir, "trading-agent", "start_agent.bat")
    ]
    
    for line in lines:
        line_clean = line.rstrip('\n')
        if not line_clean:
            continue
        
        if line_clean.startswith("trading-agent"):
            depth = 0
            name = "trading-agent"
            current_path = [name]
            continue
            
        prefix_idx = max(line_clean.find("├──"), line_clean.find("└──"))
        if prefix_idx != -1:
            depth = (prefix_idx // 4) + 1
            name = line_clean[prefix_idx + 4:].strip()
            
            if name.endswith('/'):
                name = name[:-1]
                
            current_path = current_path[:depth]
            current_path.append(name)
            
            # Now accept bat files too for start_agent.bat if parsed, though we'll filter duplicates
            if any(name.endswith(ext) for ext in [".py", ".mq5", ".yaml", ".md", ".bat"]):
                full_path = os.path.join(root_dir, *current_path[1:])
                # Don't add priority files yet, they go first
                if full_path not in priority_files:
                    filepaths.append(full_path)

    # Prepend the priority files
    final_filepaths = priority_files + filepaths

    # Sort files for deterministic output
    # filepaths.sort()
    
    # Generate all_codebase.md
    with open(output_path, 'w', encoding='utf-8') as out_f:
        out_f.write("# All Codebase\n\n")
        out_f.write("This file contains the complete source code for all files listed in STRUKTUR.md.\n\n")
        
        for fp in final_filepaths:
            if not os.path.exists(fp):
                print(f"Warning: File not found: {fp}")
                continue
                
            print(f"Adding {fp}")
            ext = os.path.splitext(fp)[1][1:]
            
            # Map extension to markdown language
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
