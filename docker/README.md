# Uptime Kuma with WireGuard Multi-Host Setup

This setup configures Uptime Kuma to monitor Docker containers across multiple remote hosts using WireGuard VPN.

## Network Architecture

- **WireGuard Network**: 10.200.200.0/24
  - 10.200.200.1 - Main server (Uptime Kuma + WireGuard server)
  - 10.200.200.2 - hal-wg (Docker proxy)
  - 10.200.200.3 - plague-wg (Docker proxy)
  - 10.200.200.4 - blade-wg (Docker proxy)

## Deployment Steps

### 1. Generate WireGuard Keys

First, generate the keys for the server and each client:

```bash
# Server keys
wg genkey | tee server_private.key | wg pubkey > server_public.key

# Client keys
wg genkey | tee hal_private.key | wg pubkey > hal_public.key
wg genkey | tee plague_private.key | wg pubkey > plague_public.key
wg genkey | tee blade_private.key | wg pubkey > blade_public.key
```

### 2. Update Configuration Files

#### Main Server (wg0.conf)
Replace these placeholders in `wg0.conf`:
- `SERVER_PRIVATE_KEY_HERE` → content of `server_private.key`
- `HAL_PUBLIC_KEY_HERE` → content of `hal_public.key`
- `PLAGUE_PUBLIC_KEY_HERE` → content of `plague_public.key`
- `BLADE_PUBLIC_KEY_HERE` → content of `blade_public.key`

#### Remote Hosts
For each host directory (hal-wg, plague-wg, blade-wg), update `wg0.conf`:
- Replace `*_PRIVATE_KEY_HERE` → content of that host's private key
- Replace `SERVER_PUBLIC_KEY_HERE` → content of `server_public.key`
- Replace `SERVER_IP` → public IP or hostname of the main server

### 3. Deploy Main Server

```bash
cd /home/gabe/Projects/uptime/docker
docker-compose up -d
```

Access Uptime Kuma at: http://localhost:3001

### 4. Deploy Remote Hosts

Copy each host directory to its respective server and start:

```bash
# On hal server
cd hal-wg
docker-compose up -d

# On plague server
cd plague-wg
docker-compose up -d

# On blade server
cd blade-wg
docker-compose up -d
```

### 5. Configure Uptime Kuma

In the Uptime Kuma web interface, add Docker monitors using these endpoints:
- **hal-wg**: `tcp://10.200.200.2:2375`
- **plague-wg**: `tcp://10.200.200.3:2375`
- **blade-wg**: `tcp://10.200.200.4:2375`

## Security Notes

- The docker-socket-proxy limits access to read-only Docker API operations
- WireGuard encrypts all traffic between hosts
- Docker socket is not exposed to the public internet
- Consider adding firewall rules to limit access to port 51820 (WireGuard)

## Troubleshooting

### Check WireGuard Status
```bash
docker exec wireguard-kuma wg show
```

### Check if clients are connected
```bash
docker exec wireguard-kuma wg show wg0 peers
```

### Test connectivity from main server
```bash
docker exec uptime-kuma ping 10.200.200.2  # hal-wg
docker exec uptime-kuma ping 10.200.200.3  # plague-wg
docker exec uptime-kuma ping 10.200.200.4  # blade-wg
```

### Test Docker API access
```bash
curl http://10.200.200.2:2375/containers/json
curl http://10.200.200.3:2375/containers/json
curl http://10.200.200.4:2375/containers/json
```
