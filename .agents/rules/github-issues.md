# GitHub Issues & External Memory Protocol

This rule governs long-term technical memory and task tracking standards for `als-finder`.

## 1. Mandatory 5-Part Issue Structure

Never create vague or purely conversational issues. Every newly opened GitHub issue MUST include:
1. **Runtime Target:** Local Desktop (`./.venv`) / Cloud VM (Docker) / HPC Supercomputer (Singularity / Slurm).
2. **Affected Paths:** Exact file paths (e.g. `src/als_finder/core/grid_manager.py`), function names, and line numbers.
3. **Environment Constraints:** Required conda environment, scratch space bindings (`$SCRATCH`), memory limits (`RLIMIT_AS`), or API credentials.
4. **Explicit Anti-Patterns & Dead Ends:** Document what NOT to do, prior failed approaches, and why they broke.
5. **Verification & Definition of Done:** Exact CLI/Pytest command, batch script test, and tangible output checks (exit code 0, non-empty `.laz` tile) that prove the issue is resolved.

---

## 2. Issue Ingestion & Working Rules

When assigned or instructed to work on an existing GitHub Issue:
- **Verify Runtime & Paths:** Read referenced source files and confirm the target execution environment before touching code.
- **Check Constraints & Anti-Patterns:** Review documented dead ends to ensure the new approach does not re-introduce known failure modes.
- **Formulate Implementation Plan:** Present an implementation plan and verification command for review before modifying code.

---

## 3. Issue Closure Rules

When resolving and closing a GitHub Issue:
- **Summarize Changes:** Provide a concise breakdown of root cause and exact changes made across modules.
- **Document New Environment Quirks:** Record any newly discovered runtime edge cases, container quirks, or compiler behaviors.
- **Link Artifacts:** Explicitly reference the fix commit SHA, branch, and PR.
