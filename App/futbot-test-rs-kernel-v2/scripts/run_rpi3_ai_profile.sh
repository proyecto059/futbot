#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

BIN_PATH="${BIN_PATH:-${SCRIPT_DIR}/futbot}"
MODEL_PATH="${MODEL_PATH:-${SCRIPT_DIR}/model.onnx}"
CAMERA_URL="${CAMERA_URL:-http://192.168.4.1:81/stream}"

arch_from_file() {
    file "$1" 2>/dev/null || true
}

detect_binary_arch() {
    local info
    info="$(arch_from_file "$1")"
    if [[ "${info}" == *"AArch64"* ]]; then
        printf 'aarch64\n'
        return
    fi
    if [[ "${info}" == *"ARM, EABI5"* ]]; then
        printf 'armv7\n'
        return
    fi
    printf 'unknown\n'
}

kernel_arch() {
    uname -m 2>/dev/null || printf 'unknown\n'
}

usage() {
    cat <<'EOF'
Usage: ./run_rpi3_ai_profile.sh [futbot-args...]

Runs futbot with tuned AI defaults for Raspberry Pi.

Environment overrides:
  BIN_PATH, MODEL_PATH, CAMERA_URL,
  AI_USE_ROI, AI_STRIDE_SEARCH, AI_STRIDE_TRACK, AI_TRACK_FULLFRAME_EVERY,
  AI_HSV_TRACK_STREAK, AI_TRACK_MAX_MISSING_FRAMES, AI_CACHE_MAX_AGE,
  AI_CONF_BASE_SEARCH, AI_CONF_BASE_TRACK, AI_CONF_MIN, AI_CONF_MAX,
  AI_SMALL_BOX_AREA_PX, AI_SMALL_BOX_BONUS, AI_LOST_FRAMES_START,
  AI_LOST_BONUS_PER_FRAME, AI_LOST_BONUS_MAX, AI_CONF_FLOOR, RUST_LOG,
  FUTBOT_UI

Examples:
  ./run_rpi3_ai_profile.sh
  CAMERA_URL="http://192.168.4.1:81/stream" ./run_rpi3_ai_profile.sh
  FUTBOT_UI=false ./run_rpi3_ai_profile.sh -- --some-arg
EOF
}

if (($# > 0)); then
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
    esac
fi

if [[ ! -f "${BIN_PATH}" ]]; then
    echo "Binary not found: ${BIN_PATH}" >&2
    exit 1
fi

if [[ ! -f "${MODEL_PATH}" ]]; then
    echo "Model not found: ${MODEL_PATH}" >&2
    exit 1
fi

BIN_ARCH="$(detect_binary_arch "${BIN_PATH}")"
HOST_ARCH="$(kernel_arch)"

if [[ "${BIN_ARCH}" == "armv7" && "${HOST_ARCH}" == "aarch64" ]]; then
    echo "Binary architecture mismatch: futbot is armv7 but host kernel is aarch64." >&2
    echo "Build/deploy with --64bit, or enable 32-bit userspace compatibility on the host." >&2
    echo "Binary info: $(arch_from_file "${BIN_PATH}")" >&2
    exit 1
fi

if [[ "${BIN_ARCH}" == "aarch64" && ( "${HOST_ARCH}" == "armv7l" || "${HOST_ARCH}" == "armhf" ) ]]; then
    echo "Binary architecture mismatch: futbot is aarch64 but host is 32-bit ARM." >&2
    echo "Build/deploy with --32bit for this host." >&2
    echo "Binary info: $(arch_from_file "${BIN_PATH}")" >&2
    exit 1
fi

if ! command -v ldd >/dev/null 2>&1; then
    echo "Missing required command: ldd" >&2
    exit 1
fi

if [[ -d "${SCRIPT_DIR}/lib" ]]; then
    export LD_LIBRARY_PATH="${SCRIPT_DIR}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    if [[ -f "${SCRIPT_DIR}/lib/libonnxruntime.so" ]]; then
        export ORT_DYLIB_PATH="${SCRIPT_DIR}/lib/libonnxruntime.so"
    fi
fi

if ! ldd "${BIN_PATH}" | grep -q "libonnxruntime"; then
    cat >&2 <<'EOF'
Warning: libonnxruntime.so is not resolved by the dynamic linker.
Install it system-wide and run sudo ldconfig, or export ORT_DYLIB_PATH before running.
EOF
fi

UI_FLAG="${UI_FLAG:---ui}"
if [[ "${FUTBOT_UI:-true}" == "false" ]]; then
    UI_FLAG=""
fi

AI_USE_ROI="${AI_USE_ROI:-true}" \
AI_STRIDE_SEARCH="${AI_STRIDE_SEARCH:-10}" \
AI_STRIDE_TRACK="${AI_STRIDE_TRACK:-18}" \
AI_TRACK_FULLFRAME_EVERY="${AI_TRACK_FULLFRAME_EVERY:-12}" \
AI_HSV_TRACK_STREAK="${AI_HSV_TRACK_STREAK:-6}" \
AI_TRACK_MAX_MISSING_FRAMES="${AI_TRACK_MAX_MISSING_FRAMES:-12}" \
AI_CACHE_MAX_AGE="${AI_CACHE_MAX_AGE:-8}" \
AI_CONF_BASE_SEARCH="${AI_CONF_BASE_SEARCH:-0.18}" \
AI_CONF_BASE_TRACK="${AI_CONF_BASE_TRACK:-0.32}" \
AI_CONF_MIN="${AI_CONF_MIN:-0.12}" \
AI_CONF_MAX="${AI_CONF_MAX:-0.60}" \
AI_SMALL_BOX_AREA_PX="${AI_SMALL_BOX_AREA_PX:-2000}" \
AI_SMALL_BOX_BONUS="${AI_SMALL_BOX_BONUS:-0.08}" \
AI_LOST_FRAMES_START="${AI_LOST_FRAMES_START:-3}" \
AI_LOST_BONUS_PER_FRAME="${AI_LOST_BONUS_PER_FRAME:-0.008}" \
AI_LOST_BONUS_MAX="${AI_LOST_BONUS_MAX:-0.16}" \
AI_CONF_FLOOR="${AI_CONF_FLOOR:-0.12}" \
RUST_LOG="${RUST_LOG:-info}" \
CAMERA_URL="${CAMERA_URL}" \
"${BIN_PATH}" ${UI_FLAG} "$@"
