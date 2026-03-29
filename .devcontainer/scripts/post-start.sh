#!/usr/bin/env bash
set -euo pipefail

# Make Docker CLI/API compatibility predictable for this devcontainer daemon.
export DOCKER_API_VERSION="${DOCKER_API_VERSION:-1.43}"

if [ ! -S /var/run/docker.sock ]; then
  exit 0
fi

# Try to align docker group with socket gid for long-term stability.
sock_gid="$(stat -c '%g' /var/run/docker.sock)"
docker_gid="$(getent group docker | cut -d: -f3 || true)"

if [ -n "$docker_gid" ] && [ "$docker_gid" != "$sock_gid" ]; then
  if ! getent group "$sock_gid" >/dev/null 2>&1; then
    sudo -n groupmod -g "$sock_gid" docker >/dev/null 2>&1 || true
  fi
fi

# Ensure current remote user belongs to docker (effective next session).
sudo -n usermod -aG docker "$USER" >/dev/null 2>&1 || true

# Prefer secure group-based access.
sudo -n chown root:docker /var/run/docker.sock >/dev/null 2>&1 || true
sudo -n chmod 660 /var/run/docker.sock >/dev/null 2>&1 || true

# If the current session still cannot talk to Docker, fall back to permissive mode.
# This avoids VS Code Docker extension lockout in already-running sessions.
if ! docker info >/dev/null 2>&1; then
  sudo -n chmod 666 /var/run/docker.sock >/dev/null 2>&1 || true
fi

exit 0
