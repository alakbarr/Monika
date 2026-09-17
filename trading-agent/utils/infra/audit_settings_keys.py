import os
import yaml
import re

def flatten_dict(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def audit_keys():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    settings_path = os.path.join(base_dir, 'trading-agent', 'config', 'settings.yaml')
    if not os.path.exists(settings_path):
        settings_path = os.path.join(base_dir, 'config', 'settings.yaml')
    if not os.path.exists(settings_path):
        print(f"settings.yaml not found at {settings_path}")
        return

    with open(settings_path, 'r', encoding='utf-8') as f:
        settings = yaml.safe_load(f) or {}

    root_keys = set(settings.keys())
    flat_settings = flatten_dict(settings)
    valid_keys = set(flat_settings.keys())
    print(f"Loaded {len(valid_keys)} flattened keys ({len(root_keys)} root sections) from settings.yaml")

    code_keys = set()
    for root, dirs, files in os.walk(base_dir):
        if any(ignored in root for ignored in [".git", "__pycache__", "venv", ".pytest_cache", "node_modules"]):
            continue
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        matches = re.findall(r'settings(?:\.get\([\'"]([a-zA-Z0-9_]+)[\'"]|\[[\'"]([a-zA-Z0-9_]+)[\'"])', content)
                        for m1, m2 in matches:
                            key = m1 or m2
                            if key:
                                code_keys.add(key)
                except Exception:
                    pass

    missing_root = [k for k in sorted(code_keys) if k not in root_keys]
    print(f"Found {len(code_keys)} unique root keys queried in python files.")
    if missing_root:
        print(f"Notice: {len(missing_root)} keys queried that are not top-level sections in settings.yaml: {missing_root[:10]}...")
    else:
        print("All queried root settings keys found in settings.yaml.")

if __name__ == '__main__':
    audit_keys()
