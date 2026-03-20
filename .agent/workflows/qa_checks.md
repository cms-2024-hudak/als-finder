---
description: Run code quality checks and tests
---

# Test & Lint Workflow

## Steps

1.  **Format**
    -   `black src/ tests/`

2.  **Lint**
    -   `ruff check src/ tests/`

3.  **Type Check**
    -   `mypy src/`

4.  **Unit Tests**
    -   `pytest tests/`

// turbo-all
