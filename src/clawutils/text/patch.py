import argparse
import sys
import os

def patch_file(file_path, text, mode, marker=None):
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = ""
    if mode == 'prepend':
        new_content = text + "\n" + content
    elif mode == 'append':
        new_content = content.rstrip() + "\n\n" + text + "\n"
    elif mode == 'after':
        if not marker:
            print("ERROR: Mode 'after' requires --marker")
            sys.exit(1)
        if marker not in content:
            print(f"ERROR: Marker '{marker}' not found in file")
            sys.exit(1)
        
        parts = content.split(marker, 1)
        new_content = parts[0] + marker + "\n" + text + parts[1]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"SUCCESS: Patched {file_path} (Mode: {mode})")

def main():
    parser = argparse.ArgumentParser(description=\"Precision Text Patcher for clawutils\")
    parser.add_argument(\"--file\", required=True, help=\"Target file path\")
    parser.add_argument(\"--text\", required=True, help=\"Text to insert\")
    parser.add_argument(\"--mode\", choices=['prepend', 'append', 'after'], required=True, help=\"Patch mode\")
    parser.add_argument(\"--marker\", help=\"Marker for 'after' mode\")
    
    args = parser.parse_args()
    patch_file(args.file, args.text, args.mode, args.marker)

if __name__ == \"__main__\":
    main()
