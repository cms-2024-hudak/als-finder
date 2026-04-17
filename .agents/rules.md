---
description: Documentation Maintenance Rules
---

# Documentation Rules

## 1. Sync Logic
-   **Code ↔ Docs**: If you change the code behavior (arguments, features, outputs), you MUST update the corresponding documentation immediately.
-   **PLAN.md**: This is a living document. Mark tasks as `[x]` when completed. Add new constraints or steps as they are discovered.

## 2. Required Documentation
-   **README.md**: Must contain:
    -   Project Title & Description
    -   Installation Instructions (Docker & Local)
    -   Basic Usage Examples
    -   Current Status/badges
-   **docs/**:
    -   `PLAN.md`: Implementation roadmap.
    -   `API.md`: (Future) Auto-generated or manual API reference.
    -   `Architecture.md`: (Optional) Diagram/text explaining the provider -> download flow.

## 3. Docstrings
-   Code is not "done" until it is documented.
-   See `python_standards.md` for format.
---
description: Rules for Version Control and Checkpointing
---

# Git & Checkpointing Rules

## 1. Commit Granularity
-   **Atomic Commits**: Commit one logical change at a time. Do not bundle refactors with feature additions.
-   **Frequency**: "Checkpoint" (commit) often. Ideally, after every successful step or file creation/modification that reaches a stable state.
-   **Safety**: Always commit before attempting a risky operation (e.g., large refactor, file deletion).

## 2. Commit Message Convention
Follow the Conventional Commits specification:
`type(scope): description`

-   **Types**:
    -   `feat`: A new feature
    -   `fix`: A bug fix
    -   `docs`: Documentation only changes
    -   `style`: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
    -   `refactor`: A code change that neither fixes a bug nor adds a feature
    -   `perf`: A code change that improves performance
    -   `test`: Adding missing tests or correcting existing tests
    -   `chore`: Changes to the build process or auxiliary tools and libraries
    -   `wip`: Work in progress (use sparingly, amend later if possible)

-   **Example**:
    -   `feat(opentopo): implement search function for global datasets`
    -   `docs(readme): update installation instructions`
    -   `chore(deps): add pdal to requirements`

## 3. Branching (If applicable)
-   Main development happens on the current branch unless instructed otherwise.
-   If experimenting, creating a temporary branch is encouraged.
---
description: Python Development Guidelines and Standards
---

# Python Development Rules

## 1. Code Style & Formatting
-   **Formatter**: Use `black` for code formatting.
-   **Linter**: Use `ruff` or `flake8` for linting.
-   **Imports**: Sort imports using `isort` (or `ruff`'s import sorting).
-   **Line Length**: 88 characters (Black default).

## 2. Type Hinting
-   **Mandatory**: All function signatures (arguments and return types) MUST have type hints.
-   **Static Analysis**: Code must pass `mypy` strict mode checks.
-   **Variables**: Type hint complex variables where inference is ambiguous.

## 3. Documentation
-   **Docstrings**: All modules, classes, and public functions must have Google-style docstrings.
    -   *Example*:
        ```python
        def fetch_data(roi: dict) -> pd.DataFrame:
            """Fetches data for a given region.

            Args:
                roi (dict): The region of interest geometry.

            Returns:
                pd.DataFrame: Metadata of found datasets.
            """
        ```
-   **Comments**: Use comments to explain *why*, not *what*.

## 4. Testing
-   **Framework**: Use `pytest`.
-   **Coverage**: Aim for high test coverage, particularly for core logic in `providers/`.
-   **Fixtures**: Use `conftest.py` for shared fixtures (e.g., sample ROIs).

## 5. File Handling
-   **Pathlib**: ALWAYS use `pathlib.Path` instead of `os.path` for file manipulation.
-   **Context Managers**: Use `with` statements for opening files.
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
