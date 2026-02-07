---
description: Setup local development environment
---

# Local Development Setup

## 1. Create Virtual Environment
We use a specific venv named `als-finder-env` to avoid conflicts.

```bash
python3 -m venv als-finder-env
source als-finder-env/bin/activate
pip install --upgrade pip
```

## 2. Install Dependencies
```bash
pip install -r requirements.txt
pip install -e .  # Install package in editable mode
```

## 3. VS Code Configuration
Select the interpreter path: `./als-finder-env/bin/python`
