#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

ARCH="${ARCH:-32}"
TARGET="${TARGET:-}"
BIN_NAME="${BIN_NAME:-futbot}"
FEATURES="${FEATURES:-ai}"
DOCKER_IMAGE="${DOCKER_IMAGE:-}"
DOCKERFILE="${DOCKERFILE:-}"
REMOTE_HOST="${REMOTE_HOST:-rasp1@raspberrypi}"
REMOTE_DIR="${REMOTE_DIR:-}"
DIST_DIR="${DIST_DIR:-}"
BUILD_IMAGE="${BUILD_IMAGE:-1}"
BUNDLE_RUNTIME_LIBS="${BUNDLE_RUNTIME_LIBS:-1}"
OPENCV_LINK_LIBS="${OPENCV_LINK_LIBS:-opencv_dnn,opencv_highgui,opencv_videoio,opencv_video,opencv_imgcodecs,opencv_imgproc,opencv_core}"
OPENCV_LINK_PATHS="${OPENCV_LINK_PATHS:-}"
OPENCV_INCLUDE_PATHS="${OPENCV_INCLUDE_PATHS:-/usr/include/opencv4}"
OPENCV_DISABLE_PROBES="${OPENCV_DISABLE_PROBES:-pkg_config,cmake,vcpkg_cmake,vcpkg}"

ARCH_SOURCE="env-default"

infer_arch_from_target() {
    case "$1" in
        armv7-unknown-linux-gnueabihf)
            printf '32\n'
            ;;
        aarch64-unknown-linux-gnu)
            printf '64\n'
            ;;
        *)
            return 1
            ;;
    esac
}

apply_arch_defaults() {
    case "$1" in
        32)
            : "${TARGET:=armv7-unknown-linux-gnueabihf}"
            : "${DOCKER_IMAGE:=futbot-cross-arm:latest}"
            : "${DOCKERFILE:=Dockerfile.cross}"
            : "${OPENCV_LINK_PATHS:=/usr/lib/arm-linux-gnueabihf}"
            ;;
        64)
            : "${TARGET:=aarch64-unknown-linux-gnu}"
            : "${DOCKER_IMAGE:=futbot-cross-aarch64:latest}"
            : "${DOCKERFILE:=Dockerfile.cross.aarch64}"
            : "${OPENCV_LINK_PATHS:=/usr/lib/aarch64-linux-gnu}"
            ;;
        *)
            echo "Invalid architecture '$1'. Use 32 or 64." >&2
            exit 2
            ;;
    esac
}

usage() {
    cat <<'EOF'
Usage: scripts/deploy_rpi3.sh [options]

Builds futbot for Raspberry Pi, packages artifacts, and copies them via SCP.

Options:
  --arch <32|64>               Build architecture selector
  --32bit                      Alias for --arch 32
  --64bit                      Alias for --arch 64
  --remote-host <user@host>    SSH target (default: rasp1@raspberrypi)
  --remote-dir <path>          Remote directory (default: $HOME/futbot)
  --target <rust-target>       Rust target (armv7/aarch64 supported)
  --features <features>        Cargo features (default: ai)
  --bin <name>                 Binary name (default: futbot)
  --dist-dir <path>            Local staging directory
  --skip-image-build           Skip docker build for cross image
  --no-runtime-bundle          Do not bundle OpenCV/ONNX runtime libs
  -h, --help                   Show this help

Environment overrides:
  ARCH, TARGET, DOCKER_IMAGE, DOCKERFILE,
  REMOTE_HOST, REMOTE_DIR, FEATURES, BIN_NAME, DIST_DIR, BUILD_IMAGE,
  BUNDLE_RUNTIME_LIBS,
  OPENCV_LINK_LIBS, OPENCV_LINK_PATHS, OPENCV_INCLUDE_PATHS, OPENCV_DISABLE_PROBES
EOF
}

TARGET_SET="0"
if [[ -n "${TARGET}" ]]; then
    TARGET_SET="1"
fi

while (($# > 0)); do
    case "$1" in
        --arch)
            ARCH="$2"
            ARCH_SOURCE="flag"
            shift 2
            ;;
        --32bit)
            ARCH="32"
            ARCH_SOURCE="flag"
            shift
            ;;
        --64bit)
            ARCH="64"
            ARCH_SOURCE="flag"
            shift
            ;;
        --remote-host)
            REMOTE_HOST="$2"
            shift 2
            ;;
        --remote-dir)
            REMOTE_DIR="$2"
            shift 2
            ;;
        --target)
            TARGET="$2"
            TARGET_SET="1"
            shift 2
            ;;
        --features)
            FEATURES="$2"
            shift 2
            ;;
        --bin)
            BIN_NAME="$2"
            shift 2
            ;;
        --dist-dir)
            DIST_DIR="$2"
            shift 2
            ;;
        --skip-image-build)
            BUILD_IMAGE="0"
            shift
            ;;
        --no-runtime-bundle)
            BUNDLE_RUNTIME_LIBS="0"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 2
            ;;
    esac
done

if [[ "${TARGET_SET}" == "1" ]]; then
    if ! TARGET_ARCH="$(infer_arch_from_target "${TARGET}")"; then
        echo "Unsupported --target '${TARGET}'. Use armv7-unknown-linux-gnueabihf or aarch64-unknown-linux-gnu." >&2
        exit 2
    fi
    if [[ "${ARCH_SOURCE}" == "flag" && "${ARCH}" != "${TARGET_ARCH}" ]]; then
        echo "Conflicting options: --arch ${ARCH} does not match --target ${TARGET}." >&2
        exit 2
    fi
    ARCH="${TARGET_ARCH}"
fi

apply_arch_defaults "${ARCH}"

if [[ -z "${DIST_DIR}" ]]; then
    DIST_DIR="${REPO_ROOT}/dist/rpi3-${ARCH}"
fi

if [[ -z "${REMOTE_DIR}" ]]; then
    if [[ "${REMOTE_HOST}" == *"@"* ]]; then
        REMOTE_USER="${REMOTE_HOST%%@*}"
    else
        REMOTE_USER="${USER}"
    fi
    REMOTE_DIR="/home/${REMOTE_USER}/futbot"
fi

if [[ -t 0 ]]; then
    SSH_TTY_ARGS=(-t)
else
    SSH_TTY_ARGS=()
fi

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

require_cmd docker
require_cmd cross
require_cmd ssh
require_cmd scp

bundle_runtime_libs() {
    local image="$1"
    local target_triple="$2"
    local out_dir="$3"
    local opencv_dir=""
    local onnxruntime_path=""

    case "${target_triple}" in
        armv7-unknown-linux-gnueabihf)
            opencv_dir="/usr/lib/arm-linux-gnueabihf"
            ;;
        aarch64-unknown-linux-gnu)
            opencv_dir="/usr/lib/aarch64-linux-gnu"
            ;;
        *)
            echo "Runtime bundle unsupported target: ${target_triple}" >&2
            return 1
            ;;
    esac

    onnxruntime_path="$(docker run --rm "${image}" sh -lc 'if [ -e /usr/local/lib/libonnxruntime.so ]; then printf "/usr/local/lib/libonnxruntime.so\n"; fi')"

    mkdir -p "${out_dir}"

    docker run --rm \
        -v "${out_dir}:/out" \
        "${image}" \
        sh -lc "
            set -eu
            if ! ls '${opencv_dir}'/libopencv_*.so.4.2* >/dev/null 2>&1; then
                echo 'No OpenCV runtime libs found in ${opencv_dir}' >&2
                exit 1
            fi
            cp -L '${opencv_dir}'/libopencv_*.so.4.2* /out/
            if [ -n '${onnxruntime_path}' ] && [ -e '${onnxruntime_path}' ]; then
                cp -L '${onnxruntime_path}' /out/libonnxruntime.so
            fi
        "

    docker run --rm \
        -v "${out_dir}:/bundle" \
        "${image}" \
        bash -lc '
            set -euo pipefail
            case "${TARGET_TRIPLE:-}'"${target_triple}"'" in
                armv7-unknown-linux-gnueabihf)
                    target_lib_dirs="/lib/arm-linux-gnueabihf:/usr/lib/arm-linux-gnueabihf:/usr/lib"
                    ;;
                aarch64-unknown-linux-gnu)
                    target_lib_dirs="/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu:/usr/lib"
                    ;;
                *)
                    target_lib_dirs="/lib:/usr/lib"
                    ;;
            esac

            extract_needed() {
                readelf -d "$1" 2>/dev/null | sed -n "s/^.*(NEEDED).*\[\(.*\)\].*$/\1/p"
            }

            resolve_dep() {
                local dep="$1"
                IFS=":" read -r -a roots_arr <<< "${target_lib_dirs}"
                for dir in "${roots_arr[@]}"; do
                    if [[ -e "${dir}/${dep}" ]]; then
                        printf "%s\n" "${dir}/${dep}"
                        return 0
                    fi
                done
                return 1
            }

            should_skip() {
                case "$1" in
                    ld-linux-*.so.*|libc.so.6|libm.so.6|libpthread.so.0|libdl.so.2|librt.so.1|libgcc_s.so.1|libstdc++.so.6|libresolv.so.2|libnsl.so.1|libutil.so.1|libanl.so.1|libcrypt.so.1)
                        return 0
                        ;;
                    *)
                        return 1
                        ;;
                esac
            }

            declare -A seen_dep
            queue=()

            for lib in /bundle/libopencv_*.so.4.2* /bundle/libonnxruntime.so; do
                [[ -e "$lib" ]] || continue
                while IFS= read -r dep; do
                    [[ -n "$dep" ]] && queue+=("$dep")
                done < <(extract_needed "$lib")
            done

            while ((${#queue[@]})); do
                dep="${queue[0]}"
                queue=("${queue[@]:1}")

                [[ -n "$dep" ]] || continue
                [[ -n "${seen_dep[${dep}]:-}" ]] && continue
                seen_dep["$dep"]=1

                if should_skip "$dep"; then
                    continue
                fi

                if [[ -e "/bundle/$dep" ]]; then
                    while IFS= read -r nested; do
                        [[ -n "$nested" ]] && queue+=("$nested")
                    done < <(extract_needed "/bundle/$dep")
                    continue
                fi

                lib_path="$(resolve_dep "$dep" || true)"
                if [[ -z "$lib_path" || ! -e "$lib_path" ]]; then
                    echo "warning: unresolved runtime dep: $dep" >&2
                    continue
                fi

                cp -L "$lib_path" "/bundle/$dep"
                while IFS= read -r nested; do
                    [[ -n "$nested" ]] && queue+=("$nested")
                done < <(extract_needed "/bundle/$dep")
            done
        '
}

cd "${REPO_ROOT}"

if [[ "${BUILD_IMAGE}" == "1" ]]; then
    if [[ ! -f "${REPO_ROOT}/${DOCKERFILE}" ]]; then
        echo "Dockerfile not found: ${DOCKERFILE}" >&2
        exit 1
    fi
    echo "[deploy] Building cross image: ${DOCKER_IMAGE} (from ${DOCKERFILE})"
    docker build -f "${DOCKERFILE}" -t "${DOCKER_IMAGE}" .
else
    echo "[deploy] Skipping cross image build"
fi

echo "[deploy] cross build --release --target ${TARGET} --features ${FEATURES} --bin ${BIN_NAME}"
OPENCV_LINK_LIBS="${OPENCV_LINK_LIBS}" \
OPENCV_LINK_PATHS="${OPENCV_LINK_PATHS}" \
OPENCV_INCLUDE_PATHS="${OPENCV_INCLUDE_PATHS}" \
OPENCV_DISABLE_PROBES="${OPENCV_DISABLE_PROBES}" \
cross build --release --target "${TARGET}" --features "${FEATURES}" --bin "${BIN_NAME}"

ARTIFACT="${REPO_ROOT}/target/${TARGET}/release/${BIN_NAME}"
MODEL_FILE="${REPO_ROOT}/model.onnx"
RUN_SCRIPT="${REPO_ROOT}/scripts/run_rpi3_ai_profile.sh"

if [[ ! -f "${ARTIFACT}" ]]; then
    echo "Build artifact not found: ${ARTIFACT}" >&2
    exit 1
fi
if [[ ! -f "${MODEL_FILE}" ]]; then
    echo "Model file not found: ${MODEL_FILE}" >&2
    exit 1
fi
if [[ ! -f "${RUN_SCRIPT}" ]]; then
    echo "Run script not found: ${RUN_SCRIPT}" >&2
    exit 1
fi

mkdir -p "${DIST_DIR}"
cp "${ARTIFACT}" "${DIST_DIR}/${BIN_NAME}"
cp "${MODEL_FILE}" "${DIST_DIR}/model.onnx"
cp "${RUN_SCRIPT}" "${DIST_DIR}/run_rpi3_ai_profile.sh"
chmod +x "${DIST_DIR}/${BIN_NAME}" "${DIST_DIR}/run_rpi3_ai_profile.sh"

if [[ "${BUNDLE_RUNTIME_LIBS}" == "1" ]]; then
    echo "[deploy] Bundling runtime libs into ${DIST_DIR}/lib"
    rm -rf "${DIST_DIR}/lib"
    bundle_runtime_libs "${DOCKER_IMAGE}" "${TARGET}" "${DIST_DIR}/lib"
fi

echo "[deploy] Preparing remote dir: ${REMOTE_HOST}:${REMOTE_DIR}"
ssh "${SSH_TTY_ARGS[@]}" "${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}'"

echo "[deploy] Copying futbot + model.onnx + run script"
scp "${DIST_DIR}/${BIN_NAME}" "${DIST_DIR}/model.onnx" "${DIST_DIR}/run_rpi3_ai_profile.sh" "${REMOTE_HOST}:${REMOTE_DIR}/"
if [[ -d "${DIST_DIR}/lib" ]]; then
    echo "[deploy] Copying bundled runtime libs"
    scp -r "${DIST_DIR}/lib" "${REMOTE_HOST}:${REMOTE_DIR}/"
fi

echo "[deploy] Fixing executable permissions on remote"
ssh "${SSH_TTY_ARGS[@]}" "${REMOTE_HOST}" "chmod +x '${REMOTE_DIR}/${BIN_NAME}' '${REMOTE_DIR}/run_rpi3_ai_profile.sh'"

echo ""
echo "Done. On Raspberry Pi run:"
echo "  cd ${REMOTE_DIR} && ./run_rpi3_ai_profile.sh"
