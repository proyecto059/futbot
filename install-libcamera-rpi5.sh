#!/bin/bash
set -euo pipefail

echo "============================================"
echo " Install libcamera with RPi 5 / PiSP support"
echo " Target: Ubuntu 24.04 on Raspberry Pi 5"
echo "============================================"

LOG="/tmp/libcamera-install.log"
exec > >(tee -a "$LOG") 2>&1

START=$(date +%s)

# ──────────────────────────────────────────
# 1. Add noble-updates repo and fix packages
# ──────────────────────────────────────────
echo ""
echo "[1/7] Adding noble-updates repo and fixing packages..."
echo "--------------------------------------------------------"
SOURCES_FILE="/etc/apt/sources.list.d/ubuntu.sources"
if ! grep -q "noble-updates" "$SOURCES_FILE" 2>/dev/null; then
    sudo tee -a "$SOURCES_FILE" > /dev/null << 'REPOEOF'

Types: deb
URIs: http://ports.ubuntu.com/ubuntu-ports/
Suites: noble-updates
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
REPOEOF
    echo "Added noble-updates repo."
fi

sudo apt update
sudo dpkg --configure -a
sudo apt --fix-broken install -y
sudo DEBIAN_FRONTEND=noninteractive apt full-upgrade -y
echo "[1/7] Done."

# ──────────────────────────────────────────
# 2. Install build dependencies
# ──────────────────────────────────────────
echo ""
echo "[2/7] Installing build dependencies..."
echo "------------------------------------------"
sudo apt install -y \
    build-essential meson ninja-build pkg-config \
    libgnutls28-dev libssl-dev libboost-dev \
    libglib2.0-dev libevent-dev \
    libyaml-cpp-dev libspdlog-dev \
    pybind11-dev \
    python3-yaml python3-ply python3-jinja2 \
    python3-sphinx python3-pip \
    libdrm-dev libudev-dev \
    gstreamer1.0-tools libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    git cmake

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies. Check $LOG"
    exit 1
fi
echo "[2/7] Done."

# ──────────────────────────────────────────
# 3. Remove Ubuntu's generic libcamera
# ──────────────────────────────────────────
echo ""
echo "[3/7] Removing Ubuntu's generic libcamera packages..."
echo "------------------------------------------"
sudo apt remove -y libcamera0.2 libcamera-tools libcamera-ipa \
    libcamera-v4l2 libcamera-dev python3-libcamera \
    gstreamer1.0-libcamera 2>/dev/null || true
sudo apt autoremove -y 2>/dev/null || true
echo "[3/7] Done."

# ──────────────────────────────────────────
# 4. Clone Raspberry Pi's libcamera
# ──────────────────────────────────────────
echo ""
echo "[4/7] Cloning Raspberry Pi libcamera repo..."
echo "------------------------------------------"
BUILD_DIR="$HOME/libcamera-build"
rm -rf "$BUILD_DIR"
git clone --depth=1 https://github.com/raspberrypi/libcamera.git "$BUILD_DIR"
echo "[4/7] Done."

# ──────────────────────────────────────────
# 5. Configure with RPi 5 pipelines
# ──────────────────────────────────────────
echo ""
echo "[5/7] Configuring build (pipelines: rpi/vc4, rpi/pisp)..."
echo "------------------------------------------"
cd "$BUILD_DIR"
meson setup build \
    --buildtype=release \
    --prefix=/usr \
    --libdir=lib/aarch64-linux-gnu \
    -Dpipelines=rpi/vc4,rpi/pisp \
    -Dipas=rpi/vc4 \
    -Dv4l2=enabled \
    -Dgstreamer=enabled \
    -Dpycamera=enabled \
    -Ddocumentation=disabled \
    -Dcam=enabled
echo "[5/7] Done."

# ──────────────────────────────────────────
# 6. Compile
# ──────────────────────────────────────────
echo ""
echo "[6/7] Compiling (this takes ~5-10 min on RPi 5)..."
echo "------------------------------------------"
NPROC=$(nproc)
echo "Using $NPROC cores..."
meson compile -C build -j"$NPROC"
echo "[6/7] Done."

# ──────────────────────────────────────────
# 7. Install
# ──────────────────────────────────────────
echo ""
echo "[7/7] Installing..."
echo "------------------------------------------"
sudo meson install -C build
sudo ldconfig

sudo apt-mark hold libcamera0.2 libcamera-tools libcamera-ipa \
    libcamera-v4l2 libcamera-dev python3-libcamera 2>/dev/null || true
echo "[7/7] Done."

# ──────────────────────────────────────────
# Verification
# ──────────────────────────────────────────
END=$(date +%s)
ELAPSED=$(( END - START ))

echo ""
echo "============================================"
echo " Installation complete! (${ELAPSED}s)"
echo "============================================"
echo ""
echo "Pipeline handlers installed:"
find /usr/lib/aarch64-linux-gnu/libcamera/ -name "*.so" -not -name "v4l2*" 2>/dev/null | sort || true
echo ""
echo "Testing camera detection:"
cam -l
echo ""
echo "If the camera appears above, you're all set!"
echo "Log saved to: $LOG"
