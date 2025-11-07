# Uptime Kuma Multi-Host Monitoring Infrastructure

A complete infrastructure for monitoring Docker containers and web services across multiple hosts using [Uptime Kuma](https://github.com/louislam/uptime-kuma), WireGuard VPN, and automated monitor synchronization.

## Features

- **Multi-Host Docker Monitoring** via WireGuard VPN tunnel
- **Automatic Monitor Sync** from Traefik routes and Docker containers
- **Secure Remote Access** using WireGuard encryption
- **Read-Only Docker Socket Proxy** for security
- **Automated Configuration Scripts** for easy deployment
- **Tag-Based Organization** for managing monitors at scale

## Architecture

### Network Topology

```
┌──────────────────────────────────────────────────────────────┐
│ Main Server (10.200.200.1)                                   │
│ ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│ │ Uptime Kuma     │  │ WireGuard    │  │ Auto-Monitor     │ │
│ │ :3001           │◄─┤ Server       │  │ Python Script    │ │
│ │                 │  │ :51820/udp   │  │                  │ │
│ └────────┬────────┘  └──────────────┘  └──────────────────┘ │
└──────────┼───────────────────────────────────────────────────┘
           │ WireGuard VPN (10.200.200.0/24)
           │
    ┌──────┴──────┬──────────────┬──────────────┐
    │             │              │              │
┌───▼──────┐ ┌───▼──────┐ ┌────▼─────┐ ┌──────▼─────┐
│ hal      │ │ plague   │ │ blade    │ │ docker-    │
│ -wg      │ │ -wg      │ │ -wg      │ │ proxy-local│
│ .2:2375  │ │ .3:2375  │ │ .4:2375  │ │ :2375      │
└──────────┘ └──────────┘ └──────────┘ └────────────┘
```

### Components

1. **Main Server** (`docker/`)
   - **Uptime Kuma**: Monitoring web interface (port 3001)
   - **WireGuard Server**: VPN server for secure remote access (port 51820/udp)
   - **Auto-Monitor**: Python tool to sync Traefik routes and Docker containers
   - **docker-proxy-local**: Read-only Docker socket proxy for local containers

2. **Remote Hosts** (`configs/{hostname}-wg/`)
   - **WireGuard Client**: Connects to main server via VPN
   - **Docker Socket Proxy**: Exposes Docker API over VPN (port 2375)

3. **Auto-Monitor Tool** (`docker/auto-monitor/`)
   - Syncs Traefik HTTPS routes to HTTP(S) monitors
   - Syncs Docker running containers to Docker container monitors
   - Automatic tag management and cleanup
   - Session recovery and error handling

## Quick Start

### Prerequisites

- Docker and Docker Compose installed on all hosts
- `wireguard-tools` package installed (for key generation)
- Network access between main server and remote hosts

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd uptime
   ```

2. **Initialize server configuration**
   ```bash
   ./init_server_config.sh
   ```
   This generates WireGuard server keys and configuration.

3. **Generate client configurations**
   ```bash
   # For each remote host
   ./generate_host_config.sh hal 10.200.200.2
   ./generate_host_config.sh plague 10.200.200.3
   ./generate_host_config.sh blade 10.200.200.4
   ```
   Follow the prompts to enter your server endpoint (e.g., `uptime.example.com:51820`).

4. **Deploy main server**
   ```bash
   cd docker
   docker-compose up -d
   ```
   Access Uptime Kuma at: `http://localhost:3001`

5. **Deploy remote hosts**
   Copy each host directory to its respective server:
   ```bash
   # On hal server
   cd configs/hal-wg
   docker-compose up -d

   # On plague server
   cd configs/plague-wg
   docker-compose up -d

   # On blade server
   cd configs/blade-wg
   docker-compose up -d
   ```

6. **Configure Auto-Monitor (optional)**
   ```bash
   cd docker/auto-monitor
   cp .env.example .env
   # Edit .env with your configuration
   ```

### First-Time Uptime Kuma Setup

1. Open `http://localhost:3001` (or your configured domain)
2. Create an admin account
3. Configure Docker Hosts in Settings → Docker Hosts:
   - **Local-docker**: `tcp://docker-proxy-local:2375`
   - **hal-wg-docker**: `tcp://10.200.200.2:2375`
   - **plague-wg-docker**: `tcp://10.200.200.3:2375`
   - **blade-wg-docker**: `tcp://10.200.200.4:2375`

## Usage

### Manual Monitor Creation

You can manually create monitors in the Uptime Kuma web interface using the configured Docker hosts.

### Automated Monitor Sync

The auto-monitor tool can automatically sync monitors from Traefik and Docker:

```bash
# Enter the auto-monitor container
docker exec -it auto-monitor bash

# Run the sync
uv run sync_monitors.py

# Or with custom options
uv run sync_monitors.py --username admin --password mypass
```

See [`docker/auto-monitor/README.md`](docker/auto-monitor/README.md) for detailed configuration.

### Configuration Scripts

#### `init_server_config.sh`
Initializes the WireGuard server configuration and generates server keys.

**Usage:**
```bash
./init_server_config.sh
```

#### `generate_host_config.sh`
Generates WireGuard client configuration and Docker Compose files for a new remote host.

**Usage:**
```bash
./generate_host_config.sh <hostname> <ip_address>
```

**Example:**
```bash
./generate_host_config.sh hal 10.200.200.2
```

This script:
- Generates WireGuard client keys
- Creates client configuration file
- Creates Docker Compose file
- Updates server configuration with new peer
- Provides next-step instructions

## Project Structure

```
.
├── README.md                      # This file
├── CLAUDE.md                      # Claude Code guidance
├── init_server_config.sh          # Initialize server WireGuard config
├── generate_host_config.sh        # Generate client configurations
├── configs/                       # WireGuard configurations
│   ├── wg0.conf                  # Server WireGuard config
│   ├── server/                   # Server keys
│   │   ├── server_private.key
│   │   └── server_public.key
│   ├── hal-wg/                   # hal client config
│   │   ├── wg0.conf
│   │   ├── docker-compose.yml
│   │   └── *.key
│   ├── plague-wg/                # plague client config
│   └── blade-wg/                 # blade client config
└── docker/                       # Main server deployment
    ├── docker-compose.yml        # Main server services
    ├── README.md                 # Docker deployment guide
    └── auto-monitor/             # Auto-sync tool
        ├── README.md             # Auto-monitor documentation
        ├── sync_monitors.py      # Sync script
        ├── pyproject.toml        # Python dependencies
        └── .env.example          # Configuration template
```

## Common Commands

### WireGuard Management

```bash
# Check WireGuard status on main server
docker exec wireguard-kuma wg show

# Check connected peers
docker exec wireguard-kuma wg show wg0 peers

# Test connectivity to remote hosts
docker exec uptime-kuma ping 10.200.200.2  # hal-wg
docker exec uptime-kuma ping 10.200.200.3  # plague-wg
docker exec uptime-kuma ping 10.200.200.4  # blade-wg

# Test Docker API access
curl http://10.200.200.2:2375/containers/json
curl http://10.200.200.3:2375/containers/json
curl http://10.200.200.4:2375/containers/json
```

### Docker Management

```bash
# Main server
cd docker
docker-compose up -d          # Start all services
docker-compose logs -f        # View logs
docker-compose restart        # Restart services
docker-compose down           # Stop all services

# Remote hosts
cd configs/hal-wg             # or plague-wg, blade-wg
docker-compose up -d          # Start client
docker-compose logs -f        # View logs
```

### Auto-Monitor

```bash
# Run sync from container (recommended)
docker exec -it auto-monitor bash
uv run sync_monitors.py

# Run sync locally (alternative)
cd docker/auto-monitor
uv run sync_monitors.py
```

## Network Configuration

### WireGuard VPN Network: 10.200.200.0/24

| Host | IP Address | Services |
|------|------------|----------|
| Main Server | 10.200.200.1 | Uptime Kuma, WireGuard Server |
| hal-wg | 10.200.200.2 | Docker Proxy (port 2375) |
| plague-wg | 10.200.200.3 | Docker Proxy (port 2375) |
| blade-wg | 10.200.200.4 | Docker Proxy (port 2375) |

### Exposed Ports

- **3001**: Uptime Kuma web interface
- **51820/udp**: WireGuard VPN
- **2375**: Docker API (only accessible via WireGuard VPN)

## Security Considerations

- **WireGuard Encryption**: All traffic between hosts is encrypted
- **Read-Only Docker Socket**: The docker-socket-proxy only allows read operations
- **No Public Docker API**: Docker socket is never exposed to the public internet
- **VPN-Only Access**: Docker APIs are only accessible through the WireGuard tunnel
- **Firewall Recommendations**:
  - Limit port 51820/udp to known IP addresses
  - Use iptables or ufw to restrict access
  - Consider adding fail2ban for additional protection

## Troubleshooting

### WireGuard Connection Issues

**Symptoms**: Remote hosts can't connect to VPN

**Solutions**:
1. Check WireGuard server status:
   ```bash
   docker exec wireguard-kuma wg show
   ```

2. Verify firewall allows UDP port 51820:
   ```bash
   sudo ufw allow 51820/udp
   ```

3. Check client logs:
   ```bash
   docker logs wireguard-client-hal
   ```

4. Verify keys are correct in configuration files

### Docker API Not Accessible

**Symptoms**: Cannot reach Docker API at 10.200.200.X:2375

**Solutions**:
1. Verify WireGuard connection is established:
   ```bash
   docker exec uptime-kuma ping 10.200.200.2
   ```

2. Check docker-proxy is running on remote host:
   ```bash
   docker ps | grep docker-proxy
   ```

3. Test Docker API directly:
   ```bash
   curl http://10.200.200.2:2375/version
   ```

### Auto-Monitor Issues

**Symptoms**: Monitors not syncing correctly

**Solutions**:
1. Check Uptime Kuma credentials in `.env`
2. Verify Docker hosts are configured in Uptime Kuma UI
3. Check container logs:
   ```bash
   docker logs auto-monitor
   ```
4. Run sync manually to see error messages:
   ```bash
   docker exec -it auto-monitor bash
   uv run sync_monitors.py
   ```

See component-specific READMEs for more detailed troubleshooting:
- [`docker/README.md`](docker/README.md) - WireGuard and Docker setup
- [`docker/auto-monitor/README.md`](docker/auto-monitor/README.md) - Auto-monitor tool

## Development

### Adding a New Remote Host

1. Run the generation script:
   ```bash
   ./generate_host_config.sh <hostname> <ip_address>
   ```

2. Restart the WireGuard server:
   ```bash
   cd docker
   docker-compose restart wireguard-kuma
   ```

3. Copy the generated config to the new host and deploy:
   ```bash
   cd configs/<hostname>-wg
   docker-compose up -d
   ```

4. Configure the new Docker host in Uptime Kuma UI

### Modifying Monitor Settings

Edit `docker/auto-monitor/sync_monitors.py` to customize:
- Monitor intervals and timeouts
- Accepted status codes
- Tag behavior
- Ignore patterns

### Contributing

When making changes:
1. Test locally first
2. Update documentation
3. Follow existing code style
4. Update CLAUDE.md if architecture changes

## License

MIT

## Acknowledgments

- [Uptime Kuma](https://github.com/louislam/uptime-kuma) - Louis Lam
- [WireGuard](https://www.wireguard.com/) - Jason A. Donenfeld
- [docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) - Tecnativa
- [uptime-kuma-api](https://github.com/lucasheld/uptime-kuma-api) - lucasheld
