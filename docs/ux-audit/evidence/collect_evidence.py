import subprocess
import os

repo_root = r"D:\Monika"
target_dir = r"D:\Monika\docs\ux-audit\evidence"
os.makedirs(target_dir, exist_ok=True)

# 1. G1: Tokens & Forbidden Effects
cmds_g1 = [
    ("Raw Hex in TSX", 'git grep -n -E "#[0-9a-fA-F]{3,8}\\b" -- "trading-agent/logging_observability/dashboard/frontend/src/*.tsx" "trading-agent/logging_observability/dashboard/frontend/src/components"'),
    ("Forbidden Effects (blur, rounded-full)", 'git grep -n -E "backdrop-filter|filter:\\s*blur|blur\\(|rounded-full|from-purple|to-indigo" -- "trading-agent/logging_observability/dashboard/frontend/src"'),
    ("1.5px Non-integer Borders", 'git grep -n -E "border.*:\\s*\'?1\\.5px" -- "trading-agent/logging_observability/dashboard/frontend/src"')
]

out_g1 = []
for title, cmd in cmds_g1:
    out_g1.append("=" * 80)
    out_g1.append(f"=== {title} ===")
    out_g1.append("=" * 80)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=repo_root)
    out_g1.append(res.stdout.strip() if res.stdout.strip() else "(None found)")
    out_g1.append("")

with open(os.path.join(target_dir, "g1-tokens-and-forbidden-effects.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out_g1))

# 2. G3: Type Floor (<11px)
cmd_g3 = 'git grep -n -E "fontSize:\\s*\'?(10|9|8|7)px\'?|--text-xs:\\s*10px" -- "trading-agent/logging_observability/dashboard/frontend/src"'
res_g3 = subprocess.run(cmd_g3, shell=True, capture_output=True, text=True, cwd=repo_root)
with open(os.path.join(target_dir, "g3-type-floor-scan.txt"), "w", encoding="utf-8") as f:
    f.write(f"Total Tiny Type Violations (<11px):\n\n" + res_g3.stdout)

# 3. G4: Target Size & Dead Controls
cmd_g4 = 'git grep -n -C 2 -E "win-control-btn|aria-label=\\"(Minimize|Maximize|Close)\\"" -- "trading-agent/logging_observability/dashboard/frontend/src"'
res_g4 = subprocess.run(cmd_g4, shell=True, capture_output=True, text=True, cwd=repo_root)
with open(os.path.join(target_dir, "g4-target-and-controls-scan.txt"), "w", encoding="utf-8") as f:
    f.write(f"Target Size and Window Control Elements:\n\n" + res_g4.stdout)

# 4. G11: TUI Scan
cmd_g11 = 'git grep -n -E "Binding\\(|build_tui_css|DataTable|RichLog" -- "trading-agent/cli/tui.py"'
res_g11 = subprocess.run(cmd_g11, shell=True, capture_output=True, text=True, cwd=repo_root)
with open(os.path.join(target_dir, "g11-tui-audit.txt"), "w", encoding="utf-8") as f:
    f.write(f"TUI Architecture & Bindings Audit:\n\n" + res_g11.stdout)

print("All evidence files collected successfully.")
