---
description: Project Directory Structure and Organization
---

# Project Structure

## Top Level
-   `src/`: **Source Code**. All application logic resides here.
    -   `als_finder/`: The main package.
-   `docs/`: **Documentation**. Plans, API docs, architecture notes.
-   `.agent/`: **Agent Configuration**. Rules and workflows for the AI assistant.
-   `scratch/`: **Scratch Space**. (Gitignored) Primary workspace for debugging scripts and local `tests/`.
-   `data/`: **Local Data**. (Gitignored) Place to store input ROIs or output data during dev.
-   `output/`: **Results**. (Gitignored) Default download destination.

## Configuration Files
-   `Dockerfile`: Container definition.
-   `setup.py`: Package installation metadata.
-   `requirements.txt`: Pinned dependencies.
-   `.env`: (Gitignored) Secrets and keys.

## Rules
1.  **No Logic at Root**: Do not put python scripts at the top level. Use `src/` or `scripts/`.
2.  **Clean Root**: Only standard config files (`.gitignore`, `README.md`, etc.) belong at the root.
