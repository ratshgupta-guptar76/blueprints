# pdk/

Purpose: process design kit files and process-specific resources used in P&R and simulation.

Guidelines:
- Keep PDK content minimal in-repo; prefer a small reference and scripts to fetch large assets.
- Document required PDK version and license terms here.

Usage:
- Tools should reference PDK paths via environment variables (e.g., `PDK_ROOT`) or the `config/` folder.
