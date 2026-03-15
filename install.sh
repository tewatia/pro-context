#!/usr/bin/env bash
set -euo pipefail

# ProContext installer for macOS and Linux.
# Creates or updates a local checkout, syncs dependencies with uv,
# and optionally runs `procontext setup`.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

DEFAULT_REPO_URL="https://github.com/procontexthq/procontext.git"
DEFAULT_REF="main"
ORIGINAL_PATH="${PATH:-}"

TMPFILES=()

cleanup() {
    local path
    for path in "${TMPFILES[@]:-}"; do
        rm -rf "$path" 2>/dev/null || true
    done
}
trap cleanup EXIT

mktempfile() {
    local path
    path="$(mktemp)"
    TMPFILES+=("$path")
    printf "%s" "$path"
}

BOLD=""
INFO=""
SUCCESS=""
WARN=""
ERROR=""
MUTED=""
NC=""

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BOLD="\033[1m"
    INFO="\033[38;5;110m"
    SUCCESS="\033[38;5;78m"
    WARN="\033[38;5;214m"
    ERROR="\033[38;5;203m"
    MUTED="\033[38;5;245m"
    NC="\033[0m"
fi

ui_info() {
    printf "%b[INFO]%b %s\n" "$INFO" "$NC" "$1"
}

ui_success() {
    printf "%b[OK]%b %s\n" "$SUCCESS" "$NC" "$1"
}

ui_warn() {
    printf "%b[WARN]%b %s\n" "$WARN" "$NC" "$1"
}

ui_error() {
    printf "%b[ERROR]%b %s\n" "$ERROR" "$NC" "$1" >&2
}

ui_kv() {
    printf "  %b%-15s%b %s\n" "$MUTED" "$1" "$NC" "$2"
}

ensure_path_dir_on_path() {
    local dir="${1%/}"
    [[ -z "$dir" || ! -d "$dir" ]] && return 0

    if [[ ":$PATH:" != *":$dir:"* ]]; then
        PATH="$dir:$PATH"
    fi
}

persist_path_dir() {
    local dir="${1%/}"
    [[ -z "$dir" || ! -d "$dir" ]] && return 0

    ensure_path_dir_on_path "$dir"

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        ui_info "Would add $dir to shell profiles if needed"
        return 0
    fi

    local path_line
    path_line="export PATH=\"$dir:\$PATH\""

    local rc
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
        if [[ -f "$rc" ]] && ! grep -Fq "$path_line" "$rc"; then
            printf "%s\n" "$path_line" >> "$rc"
            ui_info "Added $dir to $rc"
        fi
    done
}

warn_path_missing() {
    local dir="${1%/}"
    local label="$2"
    [[ -z "$dir" || ! -d "$dir" ]] && return 0

    case ":$ORIGINAL_PATH:" in
        *":$dir:"*) return 0 ;;
    esac

    ui_warn "PATH may be missing $label ($dir) in new shells."
    ui_warn "Add 'export PATH=\"$dir:\$PATH\"' to your shell profile if needed."
}

finalize_uv_path() {
    local uv_path
    uv_path="$(command -v uv 2>/dev/null || true)"
    [[ -z "$uv_path" ]] && return 0

    local uv_bin_dir
    uv_bin_dir="$(dirname "$uv_path")"
    if [[ "$uv_bin_dir" == "$HOME/"* ]]; then
        persist_path_dir "$uv_bin_dir"
        warn_path_missing "$uv_bin_dir" "uv"
    fi
}

usage() {
    cat <<'EOF'
ProContext installer for macOS and Linux

Usage:
  ./install.sh [--dir PATH] [--repo URL] [--ref REF] [--no-setup] [--dry-run]

Options:
  --dir PATH    Install or update the checkout at PATH
  --repo URL    Git repository to clone or update
  --ref REF     Git branch, tag, or commit to install (default: main)
  --version REF Alias for --ref
  --no-setup    Skip the one-time `procontext setup` step
  --dry-run     Print commands without executing them
  --help        Show this help

Environment overrides:
  PROCONTEXT_INSTALL_DIR
  PROCONTEXT_REPO_URL
  PROCONTEXT_INSTALL_REF
  PROCONTEXT_NO_SETUP=1
  PROCONTEXT_DRY_RUN=1
EOF
}

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf "%b[dry-run]%b" "$INFO" "$NC"
        printf " %q" "$@"
        printf "\n"
        return 0
    fi
    "$@"
}

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

require_option_value() {
    local option="$1"
    local value="${2-}"
    if [[ -z "$value" || "$value" == --* ]]; then
        ui_error "$option requires a value."
        usage
        exit 2
    fi
}

os_name() {
    /usr/bin/uname -s 2>/dev/null || uname -s 2>/dev/null || echo "unknown"
}

is_root() {
    [[ "$(id -u)" -eq 0 ]]
}

default_install_dir() {
    case "$(os_name)" in
        Darwin)
            printf "%s" "$HOME/Library/Application Support/procontext-source"
            ;;
        Linux)
            printf "%s" "$HOME/.local/share/procontext-source"
            ;;
        *)
            printf "%s" "$HOME/.procontext-source"
            ;;
    esac
}

require_supported_os() {
    case "$(os_name)" in
        Darwin|Linux) ;;
        *)
            ui_error "This installer only supports macOS and Linux."
            exit 1
            ;;
    esac
}

refresh_user_bin_path() {
    local candidate
    for candidate in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        ensure_path_dir_on_path "$candidate"
    done
}

run_with_privilege() {
    if is_root; then
        run "$@"
        return
    fi
    if has_cmd sudo; then
        if [[ "$DRY_RUN" != "1" ]] && ! sudo -n true >/dev/null 2>&1; then
            ui_info "Administrator privileges required; you may be prompted for your password"
            sudo -v
        fi
        run sudo "$@"
        return
    fi
    return 127
}

resolve_brew_bin() {
    local brew_bin=""
    brew_bin="$(command -v brew 2>/dev/null || true)"
    if [[ -n "$brew_bin" ]]; then
        printf "%s" "$brew_bin"
        return 0
    fi
    if [[ -x "/opt/homebrew/bin/brew" ]]; then
        printf "%s" "/opt/homebrew/bin/brew"
        return 0
    fi
    if [[ -x "/usr/local/bin/brew" ]]; then
        printf "%s" "/usr/local/bin/brew"
        return 0
    fi
    return 1
}

activate_brew_for_session() {
    local brew_bin=""
    brew_bin="$(resolve_brew_bin || true)"
    if [[ -z "$brew_bin" ]]; then
        return 1
    fi
    eval "$("$brew_bin" shellenv)"
    return 0
}

is_macos_admin_user() {
    [[ "$(os_name)" != "Darwin" ]] && return 0
    is_root && return 0
    id -Gn "$(id -un)" 2>/dev/null | grep -qw "admin"
}

detect_linux_package_manager() {
    local pm
    for pm in apt-get dnf yum pacman zypper apk; do
        if has_cmd "$pm"; then
            printf "%s" "$pm"
            return 0
        fi
    done
    return 1
}

linux_package_hint() {
    local pm="$1"
    shift
    case "$pm" in
        apt-get) printf "sudo apt-get update && sudo apt-get install -y %s" "$*" ;;
        dnf) printf "sudo dnf install -y %s" "$*" ;;
        yum) printf "sudo yum install -y %s" "$*" ;;
        pacman) printf "sudo pacman -Sy --noconfirm %s" "$*" ;;
        zypper) printf "sudo zypper --non-interactive install %s" "$*" ;;
        apk) printf "sudo apk add --no-cache %s" "$*" ;;
        *) printf "Install %s manually with your package manager" "$*" ;;
    esac
}

linux_install_packages() {
    local pm
    pm="$(detect_linux_package_manager || true)"
    case "$pm" in
        apt-get)
            run_with_privilege apt-get update -qq &&
                run_with_privilege apt-get install -y -qq "$@"
            ;;
        dnf)
            run_with_privilege dnf install -y -q "$@"
            ;;
        yum)
            run_with_privilege yum install -y -q "$@"
            ;;
        pacman)
            run_with_privilege pacman -Sy --noconfirm "$@"
            ;;
        zypper)
            run_with_privilege zypper --non-interactive install "$@"
            ;;
        apk)
            run_with_privilege apk add --no-cache "$@"
            ;;
        *)
            return 1
            ;;
    esac
}

DOWNLOADER=""

ensure_downloader() {
    if has_cmd curl; then
        DOWNLOADER="curl"
        return 0
    fi
    if has_cmd wget; then
        DOWNLOADER="wget"
        return 0
    fi

    ui_info "No downloader found; attempting to install curl"
    case "$(os_name)" in
        Darwin)
            if has_cmd brew && run brew install curl; then
                DOWNLOADER="curl"
                return 0
            fi
            ui_error "curl or wget is required to install uv."
            ui_error "Install one of them and rerun this installer."
            exit 1
            ;;
        Linux)
            if linux_install_packages curl; then
                DOWNLOADER="curl"
                return 0
            fi
            local pm
            pm="$(detect_linux_package_manager || true)"
            ui_error "curl or wget is required to install uv."
            if [[ -n "$pm" ]]; then
                ui_error "Run '$(linux_package_hint "$pm" curl)' and rerun the installer."
            else
                ui_error "Install curl or wget with your package manager and rerun."
            fi
            exit 1
            ;;
    esac
}

download_file() {
    local url="$1"
    local output="$2"
    if [[ -z "$DOWNLOADER" ]]; then
        ensure_downloader
    fi
    if [[ "$DOWNLOADER" == "curl" ]]; then
        curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 1 -o "$output" "$url"
        return
    fi
    wget -q --https-only --secure-protocol=TLSv1_2 --tries=3 --timeout=20 -O "$output" "$url"
}

ensure_homebrew() {
    [[ "$(os_name)" != "Darwin" ]] && return 0

    if activate_brew_for_session; then
        ui_success "Homebrew already available"
        return 0
    fi

    if ! is_macos_admin_user; then
        ui_error "Homebrew is not installed and this macOS user is not an Administrator."
        ui_error "Use an Administrator account or have one install Homebrew first:"
        ui_error "  https://brew.sh/"
        exit 1
    fi

    ui_info "Homebrew not found; attempting installation"
    if [[ "$DRY_RUN" == "1" ]]; then
        ui_info "Would run the official Homebrew installer"
        return 0
    fi

    local tmp
    tmp="$(mktempfile)"
    download_file "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh" "$tmp"
    /bin/bash "$tmp"

    if ! activate_brew_for_session; then
        ui_error "Homebrew installation finished, but brew is still unavailable in this shell."
        ui_error "Open a new shell, ensure Homebrew is on PATH, and rerun this installer."
        exit 1
    fi

    ui_success "Homebrew installed"
}

ensure_uv() {
    refresh_user_bin_path
    if has_cmd uv; then
        finalize_uv_path
        ui_success "uv already available: $(uv --version)"
        return 0
    fi

    ui_info "uv not found; attempting installation"
    if [[ "$(os_name)" == "Darwin" ]]; then
        ensure_homebrew
    fi
    if has_cmd brew; then
        if run brew install uv; then
            refresh_user_bin_path
        fi
    fi

    if [[ "$DRY_RUN" == "1" ]]; then
        ui_success "uv would be installed"
        return 0
    fi

    if ! has_cmd uv; then
        local tmp
        tmp="$(mktempfile)"
        download_file "https://astral.sh/uv/install.sh" "$tmp"
        sh "$tmp"
        refresh_user_bin_path
    fi

    if ! has_cmd uv; then
        ui_error "uv installation did not complete successfully."
        ui_error "Try running 'curl -LsSf https://astral.sh/uv/install.sh | sh' manually,"
        ui_error "then open a new shell and rerun this installer."
        exit 1
    fi

    finalize_uv_path
    ui_success "uv ready: $(uv --version)"
}

ensure_git() {
    if has_cmd git; then
        ui_success "git already available: $(git --version)"
        return 0
    fi

    ui_info "git not found; attempting installation"
    case "$(os_name)" in
        Darwin)
            ensure_homebrew
            if has_cmd brew && run brew install git && has_cmd git; then
                ui_success "git installed: $(git --version)"
                return 0
            fi
            if [[ "$DRY_RUN" == "1" ]]; then
                ui_success "git would be installed"
                return 0
            fi
            ui_error "git is required to install ProContext from source."
            ui_error "Install it with Xcode Command Line Tools ('xcode-select --install')"
            ui_error "or Homebrew ('brew install git'), then rerun this installer."
            exit 1
            ;;
        Linux)
            if linux_install_packages git curl && has_cmd git; then
                ui_success "git installed: $(git --version)"
                return 0
            fi
            if [[ "$DRY_RUN" == "1" ]]; then
                ui_success "git would be installed"
                return 0
            fi
            local pm
            pm="$(detect_linux_package_manager || true)"
            ui_error "git is required to install ProContext from source."
            if [[ -n "$pm" ]]; then
                ui_error "Run '$(linux_package_hint "$pm" git curl)' and rerun the installer."
            else
                ui_error "Install git with your package manager and rerun."
            fi
            exit 1
            ;;
    esac
}

validate_existing_checkout() {
    if [[ ! -d "$INSTALL_DIR/.git" ]]; then
        ui_error "$INSTALL_DIR exists but is not a git checkout."
        ui_error "Choose a different --dir or remove the existing directory."
        exit 1
    fi

    if [[ ! -f "$INSTALL_DIR/pyproject.toml" ]] ||
        ! grep -qE '^name = "procontext"$' "$INSTALL_DIR/pyproject.toml"; then
        ui_error "$INSTALL_DIR does not look like a ProContext checkout."
        ui_error "Choose a different --dir or remove the existing directory."
        exit 1
    fi
}

repo_is_dirty() {
    [[ -n "$(git -C "$INSTALL_DIR" status --porcelain 2>/dev/null || true)" ]]
}

update_checkout_ref() {
    local fresh_clone="$1"

    if repo_is_dirty; then
        ui_warn "Checkout has local changes; skipping git update and using the existing files."
        return 0
    fi

    if ! run git -C "$INSTALL_DIR" fetch --tags origin; then
        if [[ "$fresh_clone" == "1" ]]; then
            ui_error "Failed to fetch repository metadata for $INSTALL_REF."
            exit 1
        fi
        ui_warn "Git fetch failed; continuing with the existing checkout."
        return 0
    fi

    if git -C "$INSTALL_DIR" ls-remote --exit-code --heads origin "$INSTALL_REF" >/dev/null 2>&1; then
        if ! run git -C "$INSTALL_DIR" checkout "$INSTALL_REF"; then
            if [[ "$fresh_clone" == "1" ]]; then
                ui_error "Failed to check out branch '$INSTALL_REF'."
                exit 1
            fi
            ui_warn "Could not switch to branch '$INSTALL_REF'; continuing with the existing checkout."
            return 0
        fi
        if ! run git -C "$INSTALL_DIR" pull --ff-only origin "$INSTALL_REF"; then
            if [[ "$fresh_clone" == "1" ]]; then
                ui_error "Failed to update branch '$INSTALL_REF' after cloning."
                exit 1
            fi
            ui_warn "Branch update failed; continuing with the existing checkout."
        fi
        return 0
    fi

    if ! run git -C "$INSTALL_DIR" checkout "$INSTALL_REF"; then
        if [[ "$fresh_clone" == "1" ]]; then
            ui_error "Could not resolve ref '$INSTALL_REF'."
            ui_error "Use --ref with a valid branch, tag, or commit and rerun."
            exit 1
        fi
        ui_warn "Could not switch to ref '$INSTALL_REF'; continuing with the existing checkout."
    fi
}

sync_repo() {
    local parent_dir
    parent_dir="$(dirname "$INSTALL_DIR")"

    if [[ ! -d "$parent_dir" ]]; then
        ui_info "Creating parent directory $parent_dir"
        run mkdir -p "$parent_dir"
    fi

    if [[ ! -e "$INSTALL_DIR" ]]; then
        ui_info "Cloning ProContext into $INSTALL_DIR"
        if ! run git clone "$REPO_URL" "$INSTALL_DIR"; then
            ui_error "Failed to clone $REPO_URL."
            ui_error "Check network access and repository permissions, then rerun this installer."
            exit 1
        fi
        update_checkout_ref "1"
        return 0
    fi

    validate_existing_checkout

    local origin_url
    origin_url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
    if [[ -n "$origin_url" && "$origin_url" != "$REPO_URL" ]]; then
        ui_warn "Existing checkout origin is '$origin_url', not '$REPO_URL'. Continuing anyway."
    fi

    ui_info "Refreshing existing checkout in $INSTALL_DIR"
    update_checkout_ref "0"
}

run_uv_sync() {
    ui_info "Syncing runtime dependencies with uv"
    if run uv sync --project "$INSTALL_DIR" --no-dev; then
        ui_success "Runtime dependencies are synced"
        return 0
    fi

    ui_error "uv sync failed, so the installation is not usable yet."
    ui_error "Fix the error above, then rerun this installer or run:"
    ui_error "  uv sync --project \"$INSTALL_DIR\" --no-dev"
    ui_error "If Python 3.12 is missing locally, uv should provision it automatically."
    exit 1
}

SETUP_STATUS="skipped"

run_registry_setup() {
    if [[ "$NO_SETUP" == "1" ]]; then
        SETUP_STATUS="skipped"
        ui_warn "Skipping one-time registry setup (--no-setup)"
        return 0
    fi

    ui_info "Running one-time registry setup"
    if run uv run --project "$INSTALL_DIR" procontext setup; then
        SETUP_STATUS="success"
        ui_success "Initial registry setup completed"
        return 0
    fi

    SETUP_STATUS="failed"
    ui_warn "ProContext is installed, but the initial registry setup did not finish."
    ui_warn "You can retry later with:"
    ui_warn "  uv run --project \"$INSTALL_DIR\" procontext setup"
    ui_warn "If the environment looks unwell, try:"
    ui_warn "  uv run --project \"$INSTALL_DIR\" procontext doctor --fix"
}

print_plan() {
    printf "\n%sProContext Installer%s\n\n" "$BOLD" "$NC"
    ui_kv "Source repo" "$REPO_URL"
    ui_kv "Install dir" "$INSTALL_DIR"
    ui_kv "Git ref" "$INSTALL_REF"
    ui_kv "Run setup" "$( [[ "$NO_SETUP" == "1" ]] && printf "no" || printf "yes" )"
    ui_kv "Dry run" "$( [[ "$DRY_RUN" == "1" ]] && printf "yes" || printf "no" )"
    printf "\n"
}

print_next_steps() {
    cat <<EOF

${BOLD}ProContext is installed${NC}
  Source checkout: $INSTALL_DIR

Run locally:
  uv run --project "$INSTALL_DIR" procontext

Claude Code MCP config:
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "$INSTALL_DIR", "procontext"]
    }
  }
}
EOF

    case "$SETUP_STATUS" in
        skipped)
            cat <<EOF

One-time registry setup was skipped.
Run this when you are ready:
  uv run --project "$INSTALL_DIR" procontext setup
EOF
            ;;
        failed)
            cat <<EOF

The code is installed, but the initial registry download still needs attention.
Retry:
  uv run --project "$INSTALL_DIR" procontext setup

If the environment looks off:
  uv run --project "$INSTALL_DIR" procontext doctor --fix
EOF
            ;;
    esac
}

resolve_config() {
    if [[ -z "${REPO_URL:-}" ]]; then
        REPO_URL="${PROCONTEXT_REPO_URL:-$DEFAULT_REPO_URL}"
    fi
    if [[ -z "${INSTALL_REF:-}" ]]; then
        INSTALL_REF="${PROCONTEXT_INSTALL_REF:-$DEFAULT_REF}"
    fi
    if [[ -z "${INSTALL_DIR:-}" ]]; then
        INSTALL_DIR="${PROCONTEXT_INSTALL_DIR:-$(default_install_dir)}"
    fi
    if [[ "${NO_SETUP:-0}" != "1" && "${PROCONTEXT_NO_SETUP:-0}" == "1" ]]; then
        NO_SETUP="1"
    fi
    if [[ "${DRY_RUN:-0}" != "1" && "${PROCONTEXT_DRY_RUN:-0}" == "1" ]]; then
        DRY_RUN="1"
    fi
}

REPO_URL=""
INSTALL_DIR=""
INSTALL_REF=""
NO_SETUP="0"
DRY_RUN="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            require_option_value "$1" "${2-}"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --repo)
            require_option_value "$1" "${2-}"
            REPO_URL="$2"
            shift 2
            ;;
        --ref)
            require_option_value "$1" "${2-}"
            INSTALL_REF="$2"
            shift 2
            ;;
        --version)
            require_option_value "$1" "${2-}"
            INSTALL_REF="$2"
            shift 2
            ;;
        --no-setup)
            NO_SETUP="1"
            shift
            ;;
        --dry-run)
            DRY_RUN="1"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            ui_error "Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
done

resolve_config
require_supported_os
print_plan
ensure_git
ensure_uv
sync_repo
run_uv_sync
run_registry_setup
print_next_steps
