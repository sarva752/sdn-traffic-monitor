#!/bin/bash
# =============================================================================
#  run_controller.sh  -  Launch POX with the traffic_monitor module
# =============================================================================
#  Assumes POX is cloned at ~/pox . Change POX_DIR if different.
# =============================================================================

POX_DIR="${POX_DIR:-$HOME/pox}"
MODULE_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$POX_DIR" ]; then
    echo "[ERROR] POX not found at $POX_DIR"
    echo "        git clone https://github.com/noxrepo/pox.git ~/pox"
    exit 1
fi

# Copy (or symlink) our module into POX's ext/ directory
mkdir -p "$POX_DIR/ext"
cp "$MODULE_DIR/traffic_monitor.py" "$POX_DIR/ext/"

echo "[INFO]  Launching POX with traffic_monitor module ..."
echo "[INFO]  Reports will be written to /tmp/traffic_monitor_report.log"
echo ""

cd "$POX_DIR"
./pox.py log.level --DEBUG  traffic_monitor
