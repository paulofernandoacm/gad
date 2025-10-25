# gad_parser.py
import re
from pathlib import Path

def parse_gad_file(filepath):
    text = Path(filepath).read_text(encoding="utf-8")
    imports = re.findall(r'use\s+chain\.(\w+)\("([^"]+)"\)\s+as\s+(\w+)', text)
    functions = re.findall(r'fn\s+(\w+)\((.*?)\)\s*:', text)
    return {
        "imports": [{"chain": c, "target": t, "alias": a} for c,t,a in imports],
        "functions": [{"name": n, "args": a.strip()} for n,a in functions],
        "raw": text
    }

if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python gad_parser.py examples/exemplo.gad")
        sys.exit(1)
    out = parse_gad_file(sys.argv[1])
    print(json.dumps(out, indent=2, ensure_ascii=False))