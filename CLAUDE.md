# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains infrastructure for monitoring Docker containers and web services using Uptime Kuma:

1. **Docker + WireGuard Setup** (`docker/`) - Multi-host Docker monitoring via WireGuard VPN
2. **Auto-Monitor Tool** (`docker/auto-monitor/`) - Python script to automatically sync Traefik routes and Docker containers with Uptime Kuma monitors
3. **Configuration Scripts** - Automated scripts to generate WireGuard configurations for server and clients

## Architecture

### Docker/WireGuard Infrastructure

The main server runs Uptime Kuma and a WireGuard server. Remote hosts (hal, plague, blade) run WireGuard clients and docker-socket-proxy to expose their Docker APIs over the VPN.

- **WireGuard Network**: 10.200.200.0/24
  - 10.200.200.1 - Main server (Uptime Kuma + WireGuard server)
  - 10.200.200.2 - hal-wg (Docker proxy)
  - 10.200.200.3 - plague-wg (Docker proxy)
  - 10.200.200.4 - blade-wg (Docker proxy)

Remote hosts expose Docker API via `tecnativa/docker-socket-proxy` with read-only access on port 2375, accessible only through the WireGuard tunnel.

### Auto-Monitor Tool

Located in `docker/auto-monitor/`, this Python tool:
- **Traefik monitoring**: Fetches HTTPS routes from one or more Traefik instances and creates HTTP(S) monitors
  - Each monitor gets two tags: "traefik" tag + group-specific tag (e.g., "Local Server", "Production")
- **Docker monitoring**: Fetches running containers from one or more Docker hosts and creates Docker container monitors
  - Each monitor gets two tags: "docker" tag + group-specific tag
  - Docker host is configured as `{GROUP}-docker` (e.g., "Local-docker")
- Uses uptime-kuma-api Python library to manage monitors
- Supports ignore patterns to exclude certain hosts
- Can reset tags to clean up accumulated incorrect tags

The tool is idempotent and includes automatic session recovery on timeout.

## Project Structure

```
.
├── README.md                      # Main project documentation
├── CLAUDE.md                      # This file
├── init_server_config.sh          # Initialize WireGuard server config and keys
├── generate_host_config.sh        # Generate client configs for new hosts
├── configs/                       # WireGuard configurations
│   ├── wg0.conf                  # Server WireGuard config
│   ├── server/                   # Server keys directory
│   │   ├── server_private.key
│   │   └── server_public.key
│   ├── hal-wg/                   # hal client configuration
│   │   ├── wg0.conf
│   │   ├── docker-compose.yml
│   │   ├── hal_private.key
│   │   └── hal_public.key
│   ├── plague-wg/                # plague client configuration
│   └── blade-wg/                 # blade client configuration
└── docker/                       # Main server deployment
    ├── docker-compose.yml        # Main services: uptime-kuma, wireguard, auto-monitor
    ├── README.md                 # Docker deployment documentation
    └── auto-monitor/             # Auto-sync tool
        ├── README.md             # Detailed auto-monitor docs
        ├── sync_monitors.py      # Main sync script
        ├── pyproject.toml        # Python dependencies (uv)
        ├── .env.example          # Configuration template
        └── uv.lock               # uv lock file
```

## Common Commands

### Configuration Scripts

**Initialize server (first-time setup):**
```bash
# Generate server WireGuard keys and initial config
./init_server_config.sh
```

**Add a new remote host:**
```bash
# Generate client config for a new host
./generate_host_config.sh <hostname> <ip_address>

# Example:
./generate_host_config.sh hal 10.200.200.2

# Then restart the WireGuard server
cd docker && docker-compose restart wireguard-kuma

# Copy configs/hal-wg to the remote host and deploy
# On remote host: cd hal-wg && docker-compose up -d
```

### Auto-Monitor Tool

**Run from Docker container (recommended):**
```bash
# Enter the auto-monitor container
docker exec -it auto-monitor bash

# Inside container, run the sync
uv run sync_monitors.py

# Or with options
uv run sync_monitors.py --username admin --password mypass
uv run sync_monitors.py --uptime-url http://uptime-kuma:3001
```

**Run locally (alternative):**
```bash
cd docker/auto-monitor

# Run the sync (requires uv installed and .env file configured)
uv run sync_monitors.py

# Or use uv's script alias
uv run sync-monitors

# Specify custom .env file location
uv run sync_monitors.py --env-file /path/to/.env

# Override credentials
uv run sync_monitors.py --username admin --password mypass

# Override Uptime Kuma URL
uv run sync_monitors.py --uptime-url https://uptime.example.com
```

Configuration via `.env` file (copy from `.env.example` in `docker/auto-monitor/`):
- `UPTIME_KUMA_URL`, `UPTIME_KUMA_USERNAME`, `UPTIME_KUMA_PASSWORD` - Uptime Kuma credentials (note: API keys not supported, must use username/password)
  - When running in Docker, use `http://uptime-kuma:3001` for the URL
- `TRAEFIK_N_URL`, `TRAEFIK_N_GROUP` - Traefik instances to sync (N = 1, 2, 3, etc.)
- `DOCKER_N_URL`, `DOCKER_N_GROUP` - Docker hosts to sync (N = 1, 2, 3, etc.)
  - URL format: `tcp://host:port` or `http://host:port`
  - Docker host name in Uptime Kuma will be `{GROUP}-docker`
  - Must configure Docker hosts in Uptime Kuma Settings → Docker Hosts before monitors will work
- `IGNORE_PATTERNS` - Comma-separated wildcard patterns to exclude hosts
- `RESET_TAGS` - Set to `true` to remove all existing tags and add only correct group tag (use once, then set back to `false`)

### Docker Deployment

```bash
# Main server (Uptime Kuma + WireGuard server)
cd docker
docker-compose up -d

# Remote hosts (deploy each to respective server)
cd configs/hal-wg    # or plague-wg, blade-wg
docker-compose up -d
```

**First-time setup:**
1. Run `./init_server_config.sh` to initialize server
2. Run `./generate_host_config.sh <hostname> <ip>` for each remote host
3. Deploy main server: `cd docker && docker-compose up -d`
4. Copy client configs to remote hosts and deploy
5. Configure Docker hosts in Uptime Kuma UI (Settings → Docker Hosts)

### WireGuard Management

```bash
# Check WireGuard status
docker exec wireguard-kuma wg show

# Check connected peers
docker exec wireguard-kuma wg show wg0 peers

# Test connectivity from main server
docker exec uptime-kuma ping 10.200.200.2  # hal-wg
docker exec uptime-kuma ping 10.200.200.3  # plague-wg
docker exec uptime-kuma ping 10.200.200.4  # blade-wg

# Test Docker API access
curl http://10.200.200.2:2375/containers/json
curl http://10.200.200.3:2375/containers/json
curl http://10.200.200.4:2375/containers/json
```

## Development Notes

### Configuration Scripts

**`init_server_config.sh`**
- Creates `configs/server/` directory if it doesn't exist
- Generates WireGuard server keys (private and public)
- Creates initial `configs/wg0.conf` with server interface configuration
- Idempotent - won't regenerate if keys/config already exist
- Server keys are stored in `configs/server/server_private.key` and `server_public.key`

**`generate_host_config.sh <hostname> <ip>`**
- Takes hostname and IP address (must be 10.200.200.X) as arguments
- Generates WireGuard client keys for the host
- Creates `configs/<hostname>-wg/` directory with:
  - `wg0.conf` - WireGuard client configuration
  - `docker-compose.yml` - Docker services (wireguard-client + docker-proxy)
  - `<hostname>_private.key` and `<hostname>_public.key` - Client keys
- Automatically appends peer configuration to server's `configs/wg0.conf`
- Prompts for server endpoint (e.g., `uptime.example.com:51820`)
- Provides next-step deployment instructions

### Auto-Monitor Tool

- Located in `docker/auto-monitor/`
- Runs in a dedicated Docker container (`auto-monitor` service) with Python 3.12 and uv pre-installed
- Uses `uv` for Python package management
- Dependencies managed in `pyproject.toml`: requests, python-socketio, websocket-client, python-dotenv, uptime-kuma-api
- HTTP monitor defaults (Traefik) configured in `sync_monitors.py`: 60s interval, 48s timeout, 200-299 accepted status codes, 10 max redirects
- Docker monitors use the container name and configured Docker host
- The tool adds a 0.2s delay between operations to reduce API load
- Session recovery is automatic - if Uptime Kuma session times out, the script re-authenticates and continues

### Key Implementation Details

- `sync_monitors.py:extract_hosts_from_traefik()` - Fetches routes from Traefik API `/api/rawdata` endpoint, filters for HTTPS entrypoints, extracts hosts using regex
- `sync_monitors.py:extract_containers_from_docker()` - Fetches running containers from Docker API `/containers/json` endpoint, extracts container names
- `sync_monitors.py:get_or_create_tag()` - Tag management with retry logic for session timeouts
- `sync_monitors.py:add_tags_to_monitor()` - Helper function to add multiple tags to a monitor with retry logic
- `sync_monitors.py:ensure_authenticated()` - Session recovery function called on authentication errors
- Tag verification runs before creating new monitors to ensure existing monitors have correct tags
- Each Traefik monitor gets two tags: "traefik" (common) and the group-specific tag
- Each Docker monitor gets two tags: "docker" (common) and the group-specific tag
- Docker monitors use `{GROUP}-docker` as the Docker host name (must be configured in Uptime Kuma first)
- Reset tags mode (`RESET_TAGS=true`) removes all tags then adds the appropriate tags (traefik/docker + group)

### Docker Setup

- Remote hosts use `network_mode: "service:docker-proxy"` to share network stack between WireGuard client and Docker proxy
- Main server uses `network_mode: "service:uptime-kuma"` to share network between WireGuard server and Uptime Kuma
- Docker socket proxy configured with read-only permissions (CONTAINERS, SERVICES, TASKS, NETWORKS, NODES, INFO, IMAGES, VOLUMES)
- Port 51820/udp exposed on main server for WireGuard connections
- `auto-monitor` service runs Python 3.12-slim, installs uv at startup, and mounts `docker/auto-monitor/` directory at `/app`
  - Uses `network_mode: "service:uptime-kuma"` to share network namespace with uptime-kuma and wireguard-kuma
  - Has access to WireGuard VPN network (10.200.200.x) to reach remote Docker proxies
  - Can reach uptime-kuma via `http://uptime-kuma:3001` (same network namespace)
  - Can reach docker-proxy-local and WireGuard Docker proxies
  - Access container via `docker exec -it auto-monitor bash`
