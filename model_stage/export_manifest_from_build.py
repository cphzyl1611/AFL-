from pathlib import Path
import re

build_path = Path("model_stage/build_dataset.py")
text = build_path.read_text(encoding="utf-8")

pairs = re.findall(r'\("([^"]+\.json)",\s*"([^"]+)"\)', text)

print("total_pairs =", len(pairs))
for name, tag in pairs:
    print(f"{name},{tag}")