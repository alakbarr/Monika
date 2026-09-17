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

def parse_filepaths_from_structure(structure_path, root_dir=None):
    if root_dir is None:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with open(structure_path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    in_block = False
    tree_lines = []
    for line in lines:
        if line.strip().startswith('```'):
            in_block = not in_block
            continue
        if in_block:
            tree_lines.append(line)

    current_stack = []
    file_list = []

    for line in tree_lines:
        if not line.strip():
            continue
        idx = 0
        name = ''
        for i, ch in enumerate(line):
            if ch not in (' ', '│', '├', '└', '─', '`'):
                idx = i
                name = line[i:].strip()
                break
        if not name:
            continue
        
        name = name.rstrip('/')
        depth = idx // 4
        
        while current_stack and current_stack[-1][0] >= depth:
            current_stack.pop()
            
        current_stack.append((depth, name))
        
        if '.' in name:
            path_parts = [item[1] for item in current_stack]
            if path_parts and path_parts[0] in ('ClaudeTrade', 'AITrade', 'TradingAgent', os.path.basename(root_dir)):
                path_parts = path_parts[1:]
            full_path = os.path.join(root_dir, *path_parts)
            file_list.append(full_path)
            
    return file_list

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    structure_path = os.path.join(root_dir, "llm_codebase_structure.md")
    with open(structure_path, 'r', encoding='utf-8') as f:
        tree_str = f.read()

    output_path = os.path.join(root_dir, "llm_bundle_for_ai.md")
    filepaths = parse_filepaths_from_structure(structure_path, root_dir=root_dir)
    
    with open(output_path, 'w', encoding='utf-8') as out_f:
        out_f.write("# LLM Codebase Bundle\n\n")
        out_f.write("This file contains the core logic, prompts, skills, and LLM orchestration code.\n\n")
        out_f.write("## Directory Structure\n\n")
        out_f.write(tree_str)
        out_f.write("\n\n")
        
        for fp in sorted(list(set(filepaths))):
            # Strip BOM just in case
            fp = fp.replace('\ufeff', '')
            if not os.path.exists(fp):
                print(f"Warning: File not found: {fp.encode('ascii', 'ignore').decode()}")
                continue
                
            print(f"Adding {fp.encode('ascii', 'ignore').decode()}")
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
