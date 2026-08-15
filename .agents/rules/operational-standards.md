# Operational Standards & Environment Boundaries

This rule governs runtime environment boundaries, anti-patterns, pre-execution checklists, and code quality standards for `als-finder`.

## 1. Environment Boundaries

| Dimension | Local Desktop (Dev) | Cloud / Server (Docker) | HPC Supercomputer (Slurm) |
| :--- | :--- | :--- | :--- |
| **Runtime** | Native Conda (`conda-forge`) in `./.venv` | Docker (`ghcr.io/...`) | Singularity / Apptainer (`als-finder.sif`) |
| **Job Model** | Interactive CLI | Interactive / Cloud Run | Decoupled Slurm Job Arrays (`--array=0-N`) |
| **Pathing** | Relative / Absolute paths | Container-mounted paths (`/workspace`) | `$SCRATCH` / Lustre / Ceph parallel storage |
| **I/O Strategy** | Full or subset download | Chunked HTTP streaming | Zero-copy single-tile streaming (`fetch-tile`) |
| **Concurrency** | CPU core auto-detection | Container CPU limits | 1 Python worker per task, multi-threaded PDAL |

### HPC Execution Constraints:
- **No Heavy I/O on Login Nodes:** Never run full downloads or multi-tile standardization on shared login nodes.
- **Decoupled Job Arrays:** HPC batch pipelines MUST use `als-finder fetch-tile --manifest <path> --tile-id ${SLURM_ARRAY_TASK_ID}` to distribute processing across compute nodes.
- **Explicit Singularity Bindings:** Always explicitly bind project directories and scratch storage:  
  `singularity exec --bind ${WORKSPACE}:${WORKSPACE},${SCRATCH}:${SCRATCH} als-finder.sif ...`

---

## 2. Anti-Patterns & Known Gotchas (Must Avoid)

- ❌ **No Logic in `cli.py`:** `cli.py` is strictly an argument parser and command dispatcher. Keep all business logic in `src/als_finder/core/`.
- ❌ **No Hardcoded Absolute Paths:** Always use `pathlib.Path` and resolve relative to `--workspace` or environment variables.
- ❌ **No Bare `subprocess.run()` for Spatial Binaries:** Never invoke `pdal` or `gdal` via bare subprocesses. Always use `execute_with_memory_limit()` from `core/standardization.py` to enforce OS-level virtual memory capping.
- ❌ **No Unclamped Thread Spawning:** Always clamp C++ multi-threading (`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `GDAL_NUM_THREADS=1`) to prevent memory exhaustion (`RLIMIT_AS`).
- ❌ **No Unprojected Metric Math:** Never calculate tile grids, buffers, or SMRF parameters in unprojected degree space (`EPSG:4326`). Always project to local UTM before spatial slicing.
- ❌ **No Stdout Pollution:** Reserve `stdout` exclusively for machine-readable JSON payloads (`--json`). Direct all logs, warnings, and progress bars strictly to `stderr`.

---

## 3. Pre-Execution 3-Step Verification Checklist

Before proposing script modifications or executing data pipelines, verify all three checkpoints:
1. **Spatial & CRS Check**: Search in `EPSG:4326` (WGS84); metric tiling and buffering in local projected UTM.
2. **Resource & Memory Audit**: Subprocesses wrapped in `execute_with_memory_limit()`; thread limits clamped; single-row SQL for tile queries.
3. **Environment & Path Isolation**: Paths dynamic and scoped to `--workspace` or `$SCRATCH`; Singularity bindings complete; clean JSON output.
