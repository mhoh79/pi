#!/usr/bin/env bash
# deploy-to-pi.sh – Sync local project files to a Raspberry Pi over SSH/rsync.
#
# Usage:
#   ./scripts/deploy-to-pi.sh [OPTIONS]
#
# Options:
#   --host      <host>    SSH host or IP  (default: $RPI_HOST)
#   --source    <path>    Local source directory  (default: .)
#   --dest      <path>    Remote destination path (default: /home/pi/app)
#   --service   <name>    systemd service name to restart (optional)
#   --restart             Restart the service after deploying (requires --service)
#   --exclude   <list>    Comma-separated rsync exclude patterns
#                         (default: .git,build*,node_modules,__pycache__)
#   --dry-run             Pass --dry-run to rsync (no files transferred)
#   -h, --help            Show this help message
#
# Environment variables (used as defaults when flags are not provided):
#   RPI_HOST    SSH host/IP for the Raspberry Pi
#   RPI_USER    SSH user on the Pi (default: pi)

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
HOST="${RPI_HOST:-}"
USER_OVERRIDE="${RPI_USER:-}"
SOURCE="."
DEST="/home/pi/app"
SERVICE=""
RESTART=false
DRY_RUN=false
EXCLUDE_RAW=".git,build*,node_modules,__pycache__"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed '1d'
  exit 0
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || { echo "ERROR: --host requires a value" >&2; exit 1; }
      HOST="$2"; shift 2 ;;
    --source)
      [[ $# -ge 2 ]] || { echo "ERROR: --source requires a value" >&2; exit 1; }
      SOURCE="$2"; shift 2 ;;
    --dest)
      [[ $# -ge 2 ]] || { echo "ERROR: --dest requires a value" >&2; exit 1; }
      DEST="$2"; shift 2 ;;
    --service)
      [[ $# -ge 2 ]] || { echo "ERROR: --service requires a value" >&2; exit 1; }
      SERVICE="$2"; shift 2 ;;
    --restart)
      RESTART=true; shift ;;
    --exclude)
      [[ $# -ge 2 ]] || { echo "ERROR: --exclude requires a value" >&2; exit 1; }
      EXCLUDE_RAW="$2"; shift 2 ;;
    --dry-run)
      DRY_RUN=true; shift ;;
    -h|--help)
      usage ;;
    *)
      echo "Unknown option: $1" >&2
      usage ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate required arguments
# ---------------------------------------------------------------------------
if [[ -z "$HOST" ]]; then
  echo "ERROR: SSH host is required. Set --host or export RPI_HOST." >&2
  exit 1
fi

if [[ ! -d "$SOURCE" ]]; then
  echo "ERROR: Source directory does not exist: $SOURCE" >&2
  exit 1
fi

if [[ "$RESTART" == true && -z "$SERVICE" ]]; then
  echo "ERROR: --restart requires --service <name>." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Build rsync exclude flags
# ---------------------------------------------------------------------------
RSYNC_EXCLUDES=()
IFS=',' read -ra EXCLUDE_PARTS <<< "$EXCLUDE_RAW"
for pattern in "${EXCLUDE_PARTS[@]}"; do
  # Trim whitespace
  pattern="${pattern#"${pattern%%[![:space:]]*}"}"
  pattern="${pattern%"${pattern##*[![:space:]]}"}"
  [[ -n "$pattern" ]] && RSYNC_EXCLUDES+=("--exclude=${pattern}")
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SSH_OPTS=(-o ConnectTimeout=5 -o BatchMode=yes)

# RPI_HOST accepts either "host" or "user@host" format.
# If it contains @, split into user and host; otherwise use USER_OVERRIDE or default "pi".
if [[ "$HOST" == *@* ]]; then
  SSH_TARGET="$HOST"
elif [[ -n "$USER_OVERRIDE" ]]; then
  SSH_TARGET="${USER_OVERRIDE}@${HOST}"
else
  SSH_TARGET="pi@${HOST}"
fi

info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
err()   { echo "[ERROR] $*" >&2; }

# ---------------------------------------------------------------------------
# Step 1: Validate SSH connectivity
# ---------------------------------------------------------------------------
info "Checking SSH connectivity to ${SSH_TARGET}…"
if ! ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" true 2>/dev/null; then
  err "Cannot connect to ${SSH_TARGET} (timeout 5 s). Check host, user, and SSH keys."
  exit 1
fi
ok "SSH connection to ${SSH_TARGET} successful."

# ---------------------------------------------------------------------------
# Step 2: Create remote destination directory
# ---------------------------------------------------------------------------
info "Ensuring remote directory exists: ${DEST}"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "mkdir -p '${DEST}'"
ok "Remote directory ready."

# ---------------------------------------------------------------------------
# Step 3: rsync
# ---------------------------------------------------------------------------
RSYNC_FLAGS=(-avz --delete)
[[ "$DRY_RUN" == true ]] && RSYNC_FLAGS+=(--dry-run)
RSYNC_FLAGS+=("${RSYNC_EXCLUDES[@]}")

# Ensure source path ends with / so rsync copies contents, not the directory itself
SOURCE_PATH="${SOURCE%/}/"

info "Syncing files…"
info "  source : ${SOURCE_PATH}"
info "  dest   : ${SSH_TARGET}:${DEST}"
[[ "$DRY_RUN" == true ]] && info "  mode   : DRY RUN (no files will be transferred)"

rsync "${RSYNC_FLAGS[@]}" \
  -e "ssh ${SSH_OPTS[*]}" \
  "${SOURCE_PATH}" \
  "${SSH_TARGET}:${DEST}"

ok "Sync complete."

# ---------------------------------------------------------------------------
# Step 4: Restart service (optional)
# ---------------------------------------------------------------------------
if [[ "$RESTART" == true ]]; then
  info "Restarting systemd service: ${SERVICE}"
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "sudo systemctl restart '${SERVICE}'"
  ok "Service '${SERVICE}' restarted."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Deployment summary"
echo "------------------------------------------------------------"
echo "  Host      : ${SSH_TARGET}"
echo "  Source    : ${SOURCE_PATH}"
echo "  Dest      : ${DEST}"
echo "  Dry run   : ${DRY_RUN}"
if [[ -n "$SERVICE" ]]; then
  echo "  Service   : ${SERVICE}"
  echo "  Restarted : ${RESTART}"
fi
echo "============================================================"
