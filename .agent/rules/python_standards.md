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
