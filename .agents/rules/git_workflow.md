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
