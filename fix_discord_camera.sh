#!/usr/bin/env bash
# ==============================================================================
# Discord Virtual Camera Fix & Setup Script (Arch Linux)
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}🔧 Setting up Virtual Camera for Discord...${NC}"

# Step 1: Install kernel module if missing
if ! modinfo v4l2loopback &>/dev/null; then
    echo -e "${YELLOW}📦 Step 1: Installing v4l2loopback-dkms and linux-headers...${NC}"
    sudo pacman -S --needed v4l2loopback-dkms linux-headers
fi

# Step 2: Load kernel module with exclusive_caps=1
echo -e "${YELLOW}🔌 Step 2: Loading v4l2loopback kernel module (exclusive_caps=1 for Discord)...${NC}"
sudo modprobe -r v4l2loopback 2>/dev/null || true
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam" exclusive_caps=1

# Ensure user is in video group
sudo usermod -a -G video "$USER" 2>/dev/null || true

# Step 3: Verify /dev/video10
if [ -e /dev/video10 ]; then
    echo -e "${GREEN}✓ Virtual camera device /dev/video10 is active!${NC}"
else
    echo -e "${YELLOW}⚠️ Video devices created:${NC}"
    ls -la /dev/video* 2>/dev/null || echo "None"
fi

echo ""
echo -e "${BOLD}🎯 Next Steps:${NC}"
echo -e "1. Start Virtual Webcam: ${CYAN}./launch.sh${NC}"
echo -e "2. Click ${BOLD}'🎬 Demo Video'${NC} (or open a video) and click ${BOLD}'Start Virtual Camera'${NC}."
echo -e "3. Fully restart Discord (${CYAN}killall Discord${NC} then reopen Discord)."
echo -e "4. In Discord Settings → Voice & Video → Camera, select ${GREEN}'VirtualCam'${NC}!"
