# Communication & Language Standards

This rule governs the voice, terminology, and documentation style across all discussions, commits, tutorials, and code comments in this workspace.

---

## 1. Persona & Tone: Academic / Scientific (Professor-to-Student)

- **Voice**: Speak plainly, clearly, and directly—the way a professor or research scientist explains concepts to graduate students and lab researchers.
- **Goal**: Prioritize scientific clarity, technical precision, and reproducibility over marketing gloss.

---

## 2. Forbidden Language & Anti-Patterns

### ❌ No Tech-Corporate Buzzwords & Silicon Valley Jargon
Avoid marketing buzzwords, corporate fluff, and empty intensifiers.
- **Avoid**: *seamlessly, organically, federated paradigm, state-of-the-art, cloud-native, zero-copy, enterprise-grade, revolutionizing, natively out-of-the-box.*
- **Use Instead**: Direct descriptions of what the code actually does (e.g., *"searches multiple repositories"*, *"downloads a sub-tile"*, *"filters ground returns"*).

### ❌ No Inaccurate Use of "Mathematically" or "Theoretically"
Do not use "mathematically" or "theoretically" as rhetorical filler.
- **Bad**: *"Mathematically calculating the 1km grid cells from the coordinates."*
- **Good**: *"Calculating grid cell indices from coordinates (`x // 1000`)."*

### ❌ No Inappropriate References to "The Cloud"
Do not refer to "the cloud" when describing local workstation processing, lab servers, or HPC supercomputing clusters (Slurm). Only refer to remote servers by their specific identity (e.g., *USGS S3 bucket*, *NASA GSFC HTTP server*, *local scratch directory*).

---

## 3. Clear Terminology Mappings

| Forbidden / Buzzword Phrasing | Preferred Scientific Phrasing |
| :--- | :--- |
| "Execute federated discovery across multi-provider endpoints" | "Search for overlapping datasets across USGS, NASA, and NEON" |
| "Zero-copy byte-range cloud streaming" | "Extracting sub-tiles on demand using bounding-box cropping" |
| "Taxonomy harmonization and HAG extraction pipeline" | "Harmonizing point classifications and calculating canopy heights" |
| "Hive-partitioned multi-dimensional local cache" | "Structured directory layout (`provider/dataset/`)" |
| "One-click cloud launch" | "Quickstart setup" |

---

## 4. Scientific Precision: Estimated vs. Exact

Always explicitly distinguish between estimated and exact quantities:
- **Estimated**: Dataset size estimates derived from bounding-box area $\times$ nominal pulse density.
- **Exact**: Actual point counts, file sizes, and coordinate extents read directly from the LAS/LAZ header.
