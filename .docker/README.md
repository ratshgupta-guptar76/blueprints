# Docker Setup

This project uses a Docker container with the `hpretl/iic-osic-tools:chipathon26` image, which includes all open-source EDA tools (Yosys, OpenROAD, Verilator, ngspice, etc.).

## Quick Start

### 1. Start the container
```bash
./scripts/eda.sh start
```

This starts the container and displays VNC access information:
```
VNC: http://localhost:80  |  vnc://localhost:5901  (pw: abc123)
```

### 2. Open a shell inside the container
```bash
./scripts/eda.sh shell
```

### 3. Run commands headlessly
```bash
./scripts/eda.sh run "cd /foss/blueprints && librelane config.json"
```

### 4. Stop the container
```bash
./scripts/eda.sh stop
```

## Configuration

Set environment variables before starting:

- `VNC_PW` — VNC password (default: `abc123`)
- `VNC_RESOLUTION` — Display resolution (default: `1920x1200`)
- `BLUEPRINTS_DIR` — Path to this repo (default: `$HOME/vlsi/blueprints`)
- `DESIGNS_DIR` — Path to external designs (default: `$HOME/eda/designs`)

Example:
```bash
export VNC_PW=mypassword
export VNC_RESOLUTION=2560x1600
./scripts/eda.sh start
```

Or create a `.env` file in the project root:
```bash
VNC_PW=mypassword
VNC_RESOLUTION=2560x1600
BLUEPRINTS_DIR=$HOME/vlsi/blueprints
DESIGNS_DIR=$HOME/eda/designs
```

## Usage

### Interactive (GUI via VNC)
1. Run `./scripts/eda.sh start`
2. Open http://localhost:80 in a browser or connect `vnc://localhost:5901`
3. Use Yosys, OpenROAD, ngspice, etc. interactively

### Headless (CLI)
Run simulations or tool flows without VNC:
```bash
./scripts/eda.sh run "cd /foss/blueprints/sim/rtl && <your simulation command>"
```

### View logs
```bash
./scripts/eda.sh logs
```

### Check status
```bash
./scripts/eda.sh status
```

## Reproducibility for Peer Review

The container provides a reproducible environment for reviewers:
1. All tools and versions are locked in the image
2. Reviewers can pull the same image and re-run simulations/flows
3. Share simulation commands via `Makefile` or scripts in `scripts/`

For peer review, document exact commands in `sim/README.md` or add them to the Makefile.
