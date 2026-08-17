#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def sync_py_tutorial(py_path: Path):
    if not py_path.exists():
        return
    text = py_path.read_text(encoding="utf-8")
    sections = text.split("# %%")
    cells = []
    md_blocks = []

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if sec.startswith("[markdown]"):
            raw_md = sec[len("[markdown]"):].strip()
            lines = []
            for line in raw_md.splitlines():
                if line.startswith("# "):
                    lines.append(line[2:])
                elif line == "#":
                    lines.append("")
                else:
                    lines.append(line)
            cleaned_md = "\n".join(lines).strip()
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": [l + "\n" for l in cleaned_md.splitlines()]
            })
            md_blocks.append(cleaned_md)
        else:
            code_lines = [l + "\n" for l in sec.splitlines()]
            cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code_lines
            })
            md_blocks.append("```python\n" + sec + "\n```")

    nb = {
        "cells": cells,
        "metadata": {
            "language_info": {"name": "python", "version": "3.11"},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }

    base = py_path.parent / py_path.stem
    ipynb_path = base.with_suffix(".ipynb")
    md_path = base.with_suffix(".md")

    with open(ipynb_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(md_blocks) + "\n")

    print(f"✓ Synchronized {ipynb_path.name} and {md_path.name} from {py_path.name}")

if __name__ == "__main__":
    tutorials_dir = Path("tutorials")
    for py_file in sorted(tutorials_dir.glob("*.py")):
        sync_py_tutorial(py_file)
