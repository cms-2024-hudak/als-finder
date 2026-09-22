#!/usr/bin/env python3
"""
Tutorial Synchronization Utility for ALS-Finder.

Keeps Markdown (.md) tutorial files and Jupyter Notebook (.ipynb) files in sync.
Supports both Markdown -> Notebook and Notebook -> Markdown directions.

Usage:
    python scripts/sync_tutorials.py           # Sync all tutorials in tutorials/ (MD -> IPYNB)
    python scripts/sync_tutorials.py --to-md   # Sync all tutorials in tutorials/ (IPYNB -> MD)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


def md_to_notebook(md_content: str) -> Dict[str, Any]:
    """Converts a Markdown document containing code fences into a Jupyter notebook dictionary."""
    cells: List[Dict[str, Any]] = []
    
    # Split content into code blocks and markdown blocks
    pattern = re.compile(r"```(python|bash|r|sh)?\n(.*?)```", re.DOTALL)
    
    last_end = 0
    for match in pattern.finditer(md_content):
        start, end = match.span()
        
        # 1. Text before code block is Markdown cell
        md_text = md_content[last_end:start].strip()
        if md_text:
            lines = [line + "\n" for line in md_text.split("\n")]
            if lines:
                lines[-1] = lines[-1].rstrip("\n")
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": lines
            })
            
        lang = match.group(1) or "python"
        code_text = match.group(2).strip()
        
        if code_text:
            lines = [line + "\n" for line in code_text.split("\n")]
            if lines:
                lines[-1] = lines[-1].rstrip("\n")
                
            # If bash block, convert lines with leading ! or %%bash for Jupyter
            if lang in ["bash", "sh"]:
                if len(lines) == 1:
                    code_lines = ["!" + l for l in lines]
                else:
                    code_lines = ["%%bash\n"] + lines
            elif lang == "r":
                code_lines = ["%%writefile script.R\n"] + lines
            else:
                code_lines = lines
                
            cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code_lines
            })
            
        last_end = end
        
    # Trailing markdown text
    remaining_text = md_content[last_end:].strip()
    if remaining_text:
        lines = [line + "\n" for line in remaining_text.split("\n")]
        if lines:
            lines[-1] = lines[-1].rstrip("\n")
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": lines
        })
        
    return {
        "cells": cells,
        "metadata": {
            "language_info": {
                "name": "python",
                "version": "3.11.0"
            },
            "orig_nbformat": 4
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }


def notebook_to_md(nb_dict: Dict[str, Any]) -> str:
    """Converts a Jupyter notebook dictionary back to clean Markdown."""
    md_parts: List[str] = []
    
    for cell in nb_dict.get("cells", []):
        cell_type = cell.get("cell_type", "markdown")
        source = cell.get("source", [])
        text = "".join(source) if isinstance(source, list) else str(source)
        
        if cell_type == "markdown":
            md_parts.append(text.strip() + "\n")
        elif cell_type == "code":
            clean_code = text.strip()
            # Clean IPython magics if converting back to pure markdown
            if clean_code.startswith("%%bash\n"):
                lang = "bash"
                clean_code = clean_code.replace("%%bash\n", "")
            elif clean_code.startswith("!"):
                lang = "bash"
                clean_code = re.sub(r"^!", "", clean_code, flags=re.MULTILINE)
            elif clean_code.startswith("%%writefile"):
                lang = "r" if ".R" in clean_code else "python"
                clean_code = re.sub(r"^%%writefile[^\n]*\n", "", clean_code)
            else:
                lang = "python"
                
            md_parts.append(f"```{lang}\n{clean_code}\n```\n")
            
    return "\n".join(md_parts).strip() + "\n"


def sync_all(tutorials_dir: Path, to_md: bool = False):
    """Synchronizes all matching pairs in the tutorials directory."""
    if not tutorials_dir.exists():
        print(f"Error: Tutorials directory not found at {tutorials_dir}")
        sys.exit(1)
        
    if to_md:
        # Sync IPYNB -> MD
        ipynb_files = list(tutorials_dir.glob("*.ipynb"))
        for ipynb_path in ipynb_files:
            md_path = ipynb_path.with_suffix(".md")
            print(f"[SYNC] {ipynb_path.name} -> {md_path.name}")
            with open(ipynb_path, "r", encoding="utf-8") as f:
                nb_data = json.load(f)
            md_content = notebook_to_md(nb_data)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
    else:
        # Sync MD -> IPYNB
        md_files = [p for p in tutorials_dir.glob("*.md") if p.name != "README.md"]
        for md_path in md_files:
            ipynb_path = md_path.with_suffix(".ipynb")
            print(f"[SYNC] {md_path.name} -> {ipynb_path.name}")
            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()
            nb_dict = md_to_notebook(md_content)
            with open(ipynb_path, "w", encoding="utf-8") as f:
                json.dump(nb_dict, f, indent=1)
                
    print("[SUCCESS] All tutorial documents synchronized.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronize Markdown tutorials with Jupyter Notebooks.")
    parser.add_argument("--to-md", action="store_true", help="Sync from .ipynb to .md (Default is .md to .ipynb)")
    parser.add_argument("--dir", default="tutorials", help="Path to tutorials directory (default: 'tutorials')")
    args = parser.parse_args()
    
    sync_all(Path(args.dir), to_md=args.to_md)
