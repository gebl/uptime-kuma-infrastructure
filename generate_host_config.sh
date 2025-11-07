#!/bin/bash
set -e

# Script to generate WireGuard client configuration for a new host
# Usage: ./generate_host_config.sh <hostname> <ip_address>
# Example: ./generate_host_config.sh hal 10.200.200.2

if [ $# -ne 2 ]; then
    echo "Usage: $0 <hostname> <ip_address>"
    echo "Example: $0 hal 10.200.200.2"
    exit 1
fi

HOSTNAME="$1"
IP_ADDRESS="$2"
CONFIG_DIR="configs/${HOSTNAME}-wg"
SERVER_KEYS_DIR="configs/server"
WG_CONF="configs/wg0.conf"

# Validate IP address format
if ! [[ $IP_ADDRESS =~ ^10\.200\.200\.[0-9]+$ ]]; then
    echo "Error: IP address must be in the format 10.200.200.X"
    exit 1
fi

# Check if config directory already exists
if [ -d "$CONFIG_DIR" ]; then
    echo "Error: Configuration directory $CONFIG_DIR already exists"
    exit 1
fi

echo "Generating configuration for host: $HOSTNAME"
echo "IP address: $IP_ADDRESS"
echo ""

# Create config directory
mkdir -p "$CONFIG_DIR"

# Generate WireGuard keys for the client
echo "Generating WireGuard keys..."
PRIVATE_KEY=$(wg genkey)
PUBLIC_KEY=$(echo "$PRIVATE_KEY" | wg pubkey)

# Save keys to files
echo "$PRIVATE_KEY" > "$CONFIG_DIR/${HOSTNAME}_private.key"
echo "$PUBLIC_KEY" > "$CONFIG_DIR/${HOSTNAME}_public.key"
chmod 600 "$CONFIG_DIR/${HOSTNAME}_private.key"

# Read server public key
if [ ! -f "$SERVER_KEYS_DIR/server_public.key" ]; then
    echo "Error: Server public key not found at $SERVER_KEYS_DIR/server_public.key"
    echo "Please generate server keys first"
    exit 1
fi

SERVER_PUBLIC_KEY=$(cat "$SERVER_KEYS_DIR/server_public.key")

# Prompt for server endpoint
read -p "Enter server endpoint (e.g., uptime.example.com:51820): " SERVER_ENDPOINT

# Create client WireGuard config
cat > "$CONFIG_DIR/wg0.conf" << EOF
[Interface]
# ${HOSTNAME}-wg private key - generate with: wg genkey
PrivateKey = $PRIVATE_KEY
Address = ${IP_ADDRESS}/24

[Peer]
# Server public key
PublicKey = $SERVER_PUBLIC_KEY
# Replace SERVER_IP with the actual public IP or hostname of the uptime-kuma server
Endpoint = $SERVER_ENDPOINT
AllowedIPs = 10.200.200.0/24
PersistentKeepalive = 25
EOF

echo "Created WireGuard client config: $CONFIG_DIR/wg0.conf"

# Create docker-compose.yml
cat > "$CONFIG_DIR/docker-compose.yml" << EOF
version: '3.8'

services:
  wireguard-client:
    image: linuxserver/wireguard:latest
    container_name: wireguard-client-${HOSTNAME}
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Chicago
    volumes:
      - ./wg0.conf:/config/wg0.conf
      - /lib/modules:/lib/modules
    sysctls:
      - net.ipv4.conf.all.src_valid_mark=1
    network_mode: "service:docker-proxy"

  docker-proxy:
    image: tecnativa/docker-socket-proxy:latest
    container_name: docker-proxy-${HOSTNAME}
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - CONTAINERS=1
      - SERVICES=1
      - TASKS=1
      - NETWORKS=1
      - NODES=1
      - INFO=1
      - IMAGES=1
      - VOLUMES=1
    ports:
      - "2375:2375"
EOF

echo "Created docker-compose.yml: $CONFIG_DIR/docker-compose.yml"

# Update server WireGuard config by appending the peer
echo ""
echo "Adding peer to server WireGuard configuration..."
cat >> "$WG_CONF" << EOF

# Peer: ${HOSTNAME}-wg
[Peer]
# ${HOSTNAME}-wg public key
PublicKey = $PUBLIC_KEY
AllowedIPs = ${IP_ADDRESS}/32
EOF

echo "✓ Peer configuration added to $WG_CONF"
echo ""

echo "Configuration generated successfully!"
echo ""
echo "Next steps:"
echo "1. Restart the wireguard-kuma container: cd docker && docker-compose restart wireguard-kuma"
echo "2. Copy $CONFIG_DIR to the target host"
echo "3. On the target host, run: cd ${HOSTNAME}-wg && docker-compose up -d"
echo "4. In Uptime Kuma UI, add Docker host: tcp://${IP_ADDRESS}:2375"
