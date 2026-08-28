#!/usr/bin/env bash
# ==============================================================================
# Virtual Webcam — One-Click Interactive Launcher
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "  __     ___      _                  _ __          __  _                         "
echo "  \ \   / (_)    | |                | |\ \        / / | |                        "
echo "   \ \_/ / _ _ __| |_ _   _  __ _  | | \ \  /\  / /__| |__   ___ __ _ _ __ ___  "
echo "    \   / | | '__| __| | | |/ _\` | | |  \ \/  \/ / _ \ '_ \ / __/ _\` | '_ \` _ \ "
echo "     | |  | | |  | |_| |_| | (_| | | |   \  /\  /  __/ |_) | (_| (_| | | | | | |"
echo "     |_|  |_|_|   \__|\__,_|\__,_| |_|    \/  \/ \___|_.__/ \___\__,_|_| |_| |_|"
echo -e "${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BOLD}🎬 Welcome to Virtual Webcam!${NC}"
echo -e "${BLUE}================================================================================${NC}"

# Check virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚙️ Setting up virtual environment for first-time use...${NC}"
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    echo -e "${GREEN}✓ Environment ready.${NC}"
fi

PYTHON=".venv/bin/python"

# Check for v4l2loopback
V4L2_LOADED=false
if lsmod 2>/dev/null | grep -q "v4l2loopback"; then
    V4L2_LOADED=true
    echo -e "${GREEN}✓ Linux virtual camera driver (v4l2loopback) is active.${NC}"
else
    echo -e "${YELLOW}⚠️  v4l2loopback kernel module is not loaded.${NC}"
    echo -e "   Applications like Discord require v4l2loopback to see the virtual camera."
fi

# Parse any CLI arguments passed to launch.sh
EXTRA_ARGS=("$@")

# If no arguments were given and v4l2loopback isn't loaded, offer quick choice
if [ ${#EXTRA_ARGS[@]} -eq 0 ] && [ "$V4L2_LOADED" = false ]; then
    echo ""
    echo -e "${BOLD}How would you like to start?${NC}"
    echo -e "  ${GREEN}[1]${NC} Load virtual camera module with sudo (${CYAN}sudo modprobe v4l2loopback...${NC})"
    echo -e "  ${GREEN}[2]${NC} Start in Demo / Mock Mode (${CYAN}zero setup, tests UI & playback${NC})"
    echo -e "  ${GREEN}[3]${NC} Generate sample test video and start in Demo Mode"
    echo -e "  ${GREEN}[4]${NC} Launch normally"
    echo ""
    read -rp "Select option [1-4] (default: 2): " choice || choice=2
    choice=${choice:-2}

    case "$choice" in
        1)
            echo -e "${CYAN}Loading v4l2loopback kernel module...${NC}"
            sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam" exclusive_caps=1 || true
            ;;
        2)
            EXTRA_ARGS+=("--mock")
            ;;
        3)
            EXTRA_ARGS+=("--mock" "--demo")
            ;;
        4)
            ;;
        *)
            EXTRA_ARGS+=("--mock")
            ;;
    esac
fi

echo -e "${GREEN}🚀 Launching Virtual Webcam Desktop App...${NC}"
"$PYTHON" -m app.main "${EXTRA_ARGS[@]}"
