---
name: "Bug or Environment Issue"
about: "Report runtime failures, HPC cluster errors, container binding mismatches, OOMs, or data pipeline bugs."
title: "bug: <concise description>"
labels: ["bug", "infrastructure"]
assignees: ""
---

### 1. Problem Description & Symptoms
<!-- Clear, concise summary of what failed and what behavior was observed. Include stack traces or error snippets. -->

```text
<Paste traceback / error log snippet here>
```

### 2. Runtime Target & Environment Context
- **Environment**: [ ] Local Desktop (Conda) | [ ] Cloud Docker | [ ] HPC Slurm (Singularity)
- **Host System / Cluster**: (e.g., WSL2 Ubuntu 22.04, SDSC Expanse, NERSC Perlmutter)
- **Container / Image / Environment Name**: (e.g., `als-finder-env`, `als-finder.sif`, `ghcr.io/...`)
- **Resource Constraints**: (e.g., Virtual Memory Limit `RLIMIT_AS`, `--mem=4G`, threads)
- **Volume Mounts / Bindings**: (e.g., `--bind /scratch/user:/scratch/user`)

### 3. Affected Components & Exact Paths
- **Files & Line Numbers**: (e.g., `src/als_finder/core/standardization.py:221`)
- **Failing Function / Module**: (e.g., `execute_with_memory_limit()`, `run_pdal_standardization()`)
- **Input Data / Spatial Bounds / Provider**: (e.g., USGS EPT, Tahoe ROI, QL1 density)

### 4. Root Cause Analysis
<!-- Why did this break? (e.g., thread explosion under RLIMIT_AS, missing variable, EPT CRS mismatch) -->

### 5. Explicit Anti-Patterns & Prior Failed Fixes
<!-- Note what does NOT work so future investigations do not repeat dead ends. -->
- ❌ **Failed Attempt 1**: (e.g., "Using preexec_fn caused multithreading fork deadlocks")
- ❌ **Anti-Pattern to Avoid**: (e.g., "Do not bypass execute_with_memory_limit()")

### 6. Verification & Definition of Done
<!-- The exact verification command and expected output proving the bug is fixed. -->
- [ ] **Reproduction / Test Command**:
  ```bash
  /home/jgreenberg/miniconda3/envs/als-finder-env/bin/pytest tests/test_*.py -k "<test_name>"
  ```
- [ ] **Physical Run Command**:
  ```bash
  als-finder <command> ...
  ```
- [ ] **Expected Output Check**:
  - Exit code `0`
  - Valid output file produced without OOM or empty point cloud
