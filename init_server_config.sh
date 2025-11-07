#!/bin/bash
set -e

# Script to initialize WireGuard server configuration if it doesn't exist
# This should be run before starting the docker-compose stack

CONFIG_DIR="configs"
SERVER_DIR="$CONFIG_DIR/server"
WG_CONF="$CONFIG_DIR/wg0.conf"

# Create directories if they don't exist
mkdir -p "$SERVER_DIR"

# Generate server keys if they don't exist
if [ ! -f "$SERVER_DIR/server_private.key" ] || [ ! -f "$SERVER_DIR/server_public.key" ]; then
    echo "Generating WireGuard server keys..."
    SERVER_PRIVATE_KEY=$(wg genkey)
    SERVER_PUBLIC_KEY=$(echo "$SERVER_PRIVATE_KEY" | wg pubkey)

    echo "$SERVER_PRIVATE_KEY" > "$SERVER_DIR/server_private.key"
    echo "$SERVER_PUBLIC_KEY" > "$SERVER_DIR/server_public.key"
    chmod 600 "$SERVER_DIR/server_private.key"

    echo "✓ Server keys generated:"
    echo "  Private key: $SERVER_DIR/server_private.key"
    echo "  Public key:  $SERVER_DIR/server_public.key"
else
    echo "✓ Server keys already exist"
    SERVER_PRIVATE_KEY=$(cat "$SERVER_DIR/server_private.key")
fi

# Create wg0.conf if it doesn't exist
if [ ! -f "$WG_CONF" ]; then
    echo "Creating WireGuard server configuration..."

    cat > "$WG_CONF" << 'EOF'
[Interface]
# Server private key - generate with: wg genkey
PrivateKey = SERVER_PRIVATE_KEY_PLACEHOLDER
Address = 10.200.200.1/24
ListenPort = 51820

# PostUp and PostDown rules for routing
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth+ -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth+ -j MASQUERADE

# Add peers below using ./generate_host_config.sh
# Example peer configuration:
# [Peer]
# PublicKey = <client_public_key>
# AllowedIPs = 10.200.200.X/32
EOF

    # Replace placeholder with actual private key
    sed -i "s|SERVER_PRIVATE_KEY_PLACEHOLDER|$SERVER_PRIVATE_KEY|g" "$WG_CONF"

    echo "✓ WireGuard server configuration created: $WG_CONF"
    echo ""
    echo "Server public key (for client configs):"
    cat "$SERVER_DIR/server_public.key"
    echo ""
    echo "Next steps:"
    echo "1. Generate client configurations using: ./generate_host_config.sh <hostname> <ip>"
    echo "2. Start the server: cd docker && docker-compose up -d"
else
    echo "✓ WireGuard server configuration already exists: $WG_CONF"
fi

echo ""
echo "Initialization complete!"
