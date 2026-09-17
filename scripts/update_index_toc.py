import os
import re

INDEX_FILE = os.path.join(os.path.dirname(__file__), "..", "INDEX.md")

def generate_toc():
    if not os.path.exists(INDEX_FILE):
        print(f"Error: {INDEX_FILE} not found.")
        return

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')

    # Find TOC start and end
    toc_start_idx = -1
    content_start_idx = -1
    
    for i, line in enumerate(lines):
        if line.strip() == "## Table of Contents":
            toc_start_idx = i
        elif (line.startswith("## Direktori Utama:") or line.startswith("## Root Directory:")) and toc_start_idx != -1:
            content_start_idx = i
            break
            
    if toc_start_idx == -1 or content_start_idx == -1:
        print("Error: Could not find '## Table of Contents' or '## Root Directory:' markers.")
        return

    # Extract headings
    headings = []
    # Regex to match ## Root Directory: ... or ### Folder: ...
    # Group 1: hashes
    # Group 2: label
    # Group 3: name
    pattern = re.compile(r'^(#{2,})\s+(Direktori Utama:|Root Directory:|Folder:)\s*(.*)', re.IGNORECASE)
    
    for i in range(content_start_idx, len(lines)):
        line = lines[i]
        match = pattern.match(line)
        if match:
            level = len(match.group(1))
            label = match.group(2)
            name = match.group(3).strip()
            
            # Remove any Markdown links or weird formatting in the name for the anchor
            clean_name = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', name)
            clean_name = clean_name.replace('`', '')
            
            # Combine label and anchor logic for GitHub markdown
            full_text = f"{label} {name}"
            full_clean = f"{label} {clean_name}".lower()
            
            # Clean anchor: lower case, replace spaces/slashes with dashes, remove special chars
            anchor = re.sub(r'[^\w\s-]', '', full_clean).replace(' ', '-')
            # Multiple dashes to single dash
            anchor = re.sub(r'-+', '-', anchor).strip('-')
            
            headings.append({
                'orig_line_idx': i,
                'level': level,
                'text': full_text,
                'anchor': anchor
            })

    # Calculate new sizes
    # new TOC format:
    # ## Table of Contents
    # *(Note: Line numbers are auto-updated by scripts/update_index_toc.py)*
    # <empty line>
    # <toc items>
    # <empty line>
    new_toc_lines_count = 3 + len(headings) + 1
    old_toc_lines_count = content_start_idx - toc_start_idx
    delta = new_toc_lines_count - old_toc_lines_count

    # Build new TOC
    new_toc_lines = [
        "## Table of Contents",
        "*(Note: Line numbers are auto-updated by `scripts/update_index_toc.py`)*",
        ""
    ]
    
    # Keep track of duplicate anchors
    anchor_counts = {}

    for h in headings:
        # Calculate new line number (1-indexed)
        new_line_num = h['orig_line_idx'] + 1 + delta
        
        # Determine indentation: ## is 0 spaces, ### is 2, #### is 4, etc.
        indent = "  " * (h['level'] - 2)
        
        # Handle duplicate anchors as GitHub does (append -1, -2, etc.)
        base_anchor = h['anchor']
        if base_anchor in anchor_counts:
            anchor_counts[base_anchor] += 1
            final_anchor = f"{base_anchor}-{anchor_counts[base_anchor]}"
        else:
            anchor_counts[base_anchor] = 0
            final_anchor = base_anchor
            
        toc_line = f"{indent}- [{h['text']}](#{final_anchor}) - Line {new_line_num}"
        new_toc_lines.append(toc_line)

    new_toc_lines.append("") # Empty line before the next section

    # Replace old TOC with new TOC
    new_file_lines = lines[:toc_start_idx] + new_toc_lines + lines[content_start_idx:]

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_file_lines))

    print(f"Successfully updated TOC in INDEX.md. Found {len(headings)} sections. Shift delta: {delta} lines.")

if __name__ == '__main__':
    generate_toc()
