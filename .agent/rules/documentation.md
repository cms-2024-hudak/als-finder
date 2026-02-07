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
