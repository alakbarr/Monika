import os
import ast
import re
import sys
import importlib.util
from pathlib import Path

stdlib = sys.stdlib_module_names
project_root = Path(__file__).resolve().parent.parent

# Known local directories/modules
local_modules = {
    'analysis', 'config', 'database', 'execution', 'indicators', 
    'logging_observability', 'risk', 'scheduler', 'telegram_bot', 
    'utils', 'graph', 'cli', 'tests', 'main', 'run_benchmark',
    'timesfm3', 'alembic', 'scripts', 'skills', 'data_sources', 
    'scrapers', 'backtest', 'benchmark', 'ea_bridge'
}

all_imports = {} # top_mod -> list of (file, lineno)
try_except_imports = [] # list of (file, lineno, mod_name)
dynamic_imports = [] # list of (file, lineno, mod_name)

scan_dirs = ['trading-agent', 'scripts']

for s_dir in scan_dirs:
    target_path = os.path.join(project_root, s_dir)
    for root, dirs, files in os.walk(target_path):
        if any(p in root for p in ['venv', '.git', 'node_modules', '.pytest_cache', '__pycache__']):
            continue
        for f in files:
            if f.endswith('.py'):
                filepath = os.path.join(root, f)
                relpath = os.path.relpath(filepath, project_root)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as fp:
                        content = fp.read()
                        
                        # Regex search for dynamic imports
                        for m in re.finditer(r'importlib\.import_module\s*\(\s*["\']([a-zA-Z0-9_\.]+)["\']', content):
                            line_no = content[:m.start()].count('\n') + 1
                            dynamic_imports.append((relpath, line_no, m.group(1)))
                        for m in re.finditer(r'__import__\s*\(\s*["\']([a-zA-Z0-9_\.]+)["\']', content):
                            line_no = content[:m.start()].count('\n') + 1
                            dynamic_imports.append((relpath, line_no, m.group(1)))
                            
                        tree = ast.parse(content, filename=filepath)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    mod = alias.name.split('.')[0]
                                    all_imports.setdefault(mod, []).append((relpath, node.lineno))
                            elif isinstance(node, ast.ImportFrom):
                                if node.module and node.level == 0:
                                    mod = node.module.split('.')[0]
                                    all_imports.setdefault(mod, []).append((relpath, node.lineno))
                            elif isinstance(node, ast.Try):
                                for handler in node.handlers:
                                    if handler.type:
                                        exc_names = [n.id for n in ast.walk(handler.type) if isinstance(n, ast.Name)]
                                        if any(x in exc_names for x in ['ImportError', 'ModuleNotFoundError', 'Exception', 'BaseException']):
                                            for subnode in node.body:
                                                if isinstance(subnode, ast.Import):
                                                    for alias in subnode.names:
                                                        try_except_imports.append((relpath, subnode.lineno, alias.name))
                                                elif isinstance(subnode, ast.ImportFrom):
                                                    if subnode.module:
                                                        try_except_imports.append((relpath, subnode.lineno, subnode.module))
                except Exception as err:
                    print(f"Error parsing {relpath}: {err}")

# Check specs for all non-stdlib non-local top modules
missing_packages = {}
found_packages = {}

all_top_candidates = set(all_imports.keys())
for _, _, d_mod in dynamic_imports:
    all_top_candidates.add(d_mod.split('.')[0])
for _, _, t_mod in try_except_imports:
    all_top_candidates.add(t_mod.split('.')[0])

for mod in sorted(all_top_candidates):
    if mod in stdlib or mod in local_modules:
        continue
    spec = importlib.util.find_spec(mod)
    if spec is None:
        missing_packages[mod] = all_imports.get(mod, [])
    else:
        found_packages[mod] = spec.origin

print("==================================================")
print(f"  DEEP CODEBASE DEPENDENCY AUDIT RESULTS")
print("==================================================")
print(f"Total External Packages Found & Available ({len(found_packages)}):")
for pkg in sorted(found_packages.keys()):
    print(f"  + {pkg}")

print(f"\nMISSING Packages ({len(missing_packages)}):")
for pkg, occurrences in missing_packages.items():
    print(f"\n[-] MISSING: {pkg}")
    for f, l in occurrences[:5]:
        print(f"    in {f}:{l}")
    if len(occurrences) > 5:
        print(f"    ... and {len(occurrences) - 5} more locations")

print("\n--- DYNAMIC IMPORTS FOUND ---")
for f, l, m in dynamic_imports:
    top = m.split('.')[0]
    is_ok = (top in stdlib) or (top in local_modules) or (importlib.util.find_spec(top) is not None)
    status = "OK" if is_ok else "MISSING"
    print(f"  [{status}] {f}:{l} -> {m}")

print("\n--- TRY-EXCEPT IMPORTS (POTENTIAL SILENT FALLBACKS) ---")
for f, l, m in try_except_imports:
    top = m.split('.')[0]
    is_ok = (top in stdlib) or (top in local_modules) or (importlib.util.find_spec(top) is not None)
    status = "OK" if is_ok else "MISSING"
    print(f"  [{status}] {f}:{l} -> {m}")
