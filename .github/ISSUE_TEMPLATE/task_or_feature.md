---
name: "Task or Feature"
about: "Propose a new pipeline feature, multi-environment integration, or architectural refactor."
title: "feat: <concise description>"
labels: ["feature", "infrastructure"]
assignees: ""
---

### 1. Summary & Objective
<!-- Concise description of what needs to be built or refactored and why. -->

### 2. Runtime Target & Environment Matrix
- [ ] Local Workstation (`conda-forge` environment)
- [ ] Cloud / Container (Docker / GHCR image)
- [ ] HPC Cluster (Slurm Batch Array / Singularity / Apptainer)

**Target Details:**
- **Target OS / Environment**: (e.g., Linux WSL2, Rocky Linux 8 / SDSC Expanse)
- **Container / SIF Path**: (if applicable)
- **Node Allocation / Resources**: (e.g., `--mem=8G`, `--cpus-per-task=2`, `$SCRATCH` partition)

### 3. Affected Components & Paths
- **Source Files**: (e.g., `src/als_finder/core/grid_manager.py`, `src/als_finder/cli.py`)
- **Key Functions / Classes**: (e.g., `export_grid_manifest()`, `stream_single_tile()`)
- **Schemas / Formats Impacted**: (e.g., `manifest.json`, `grid.gpkg`, Hive partitions)

### 4. Architectural & Environment Constraints
- **Required Credentials / Tokens**: (e.g., `OPENTOPOGRAPHY_API_KEY`, AWS unsigned)
- **Coordinate Reference Systems**: (e.g., input WGS84 `EPSG:4326` -> projected metric UTM `EPSG:32610`)
- **Memory & Concurrency Limits**: (e.g., `execute_with_memory_limit(4096)`, clamped threads)

### 5. Explicit Anti-Patterns & Pitfalls to Avoid
<!-- What NOT to do, why previous approaches failed, or constraints to respect -->
- ❌ Do NOT put business/processing logic into `cli.py`.
- ❌ Do NOT run unprojected metric math or degree-space buffer operations.
- ❌ 

### 6. Acceptance Criteria & Definition of Done
<!-- The exact verification commands and expected outputs that prove this is complete -->
- [ ] **Automated Test Command**:
  ```bash
  /home/jgreenberg/miniconda3/envs/als-finder-env/bin/pytest tests/test_*.py
  ```
- [ ] **End-to-End Pipeline Execution**:
  ```bash
  als-finder <command> --workspace ./test_workspace/ ...
  ```
- [ ] **Expected Output / Deliverable Verification**:
  - `manifest.json` updated with schema validation.
  - Standardized `.copc.laz` files generated in correct Hive partition.
