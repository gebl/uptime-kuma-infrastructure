# Uptime Kuma - Auto-Monitor (Traefik & Docker Sync)

Automatically sync Traefik host rules and Docker containers with Uptime Kuma monitors. This tool:
- Fetches all HTTPS routes from one or more Traefik instances and creates HTTP(S) monitors
- Fetches all running containers from one or more Docker hosts and creates Docker container monitors

All monitors are organized by tags/groups for easy management.

**This tool runs in a Docker container alongside Uptime Kuma** for easy deployment and management.

## Features

- ✅ Sync monitors from multiple Traefik instances
  - Creates HTTP(S) monitors for HTTPS routes
  - Adds "traefik" tag + group-specific tag
- ✅ Sync monitors from multiple Docker hosts
  - Creates Docker container monitors for running containers
  - Adds "docker" tag + group-specific tag
  - Configures Docker host as `{GROUP}-docker`
- ✅ Automatic tag/group creation and assignment
- ✅ Automatic tag verification and correction for existing monitors
- ✅ Optional tag reset mode to clean up accumulated tags
- ✅ Automatic session recovery on timeout (no manual re-runs needed)
- ✅ Only creates monitors for missing hosts/containers (idempotent)
- ✅ Configuration via `.env` file
- ✅ Customizable monitor settings
- ✅ Ignore patterns with wildcard support (excludes hosts from monitoring)
- ✅ Automatic cleanup of monitors matching ignore patterns
- ✅ Runs in Docker container with Python and uv pre-installed

## Quick Start

The auto-monitor service is included in the main `docker-compose.yml`. It starts automatically with Uptime Kuma and shares its network namespace, giving it access to:
- Uptime Kuma API at `http://uptime-kuma:3001`
- WireGuard VPN network (10.200.200.x addresses)
- Local and remote Docker proxies

1. Configure your `.env` file (see Configuration below)

2. Start the Docker stack:
   ```bash
   cd docker
   docker-compose up -d
   ```

3. Run the sync from within the container:
   ```bash
   docker exec -it auto-monitor bash
   uv run sync_monitors.py
   ```

## Installation (Local Development)

For local development without Docker:

1. Install [uv](https://github.com/astral-sh/uv):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Create a `.env` file (see Configuration below)

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Uptime Kuma Configuration
# When running in Docker, use: http://uptime-kuma:3001
# When running locally, use your external URL: https://uptime.example.com
UPTIME_KUMA_URL=http://uptime-kuma:3001
UPTIME_KUMA_USERNAME=admin
UPTIME_KUMA_PASSWORD=your_password

# Traefik Servers (you can add as many as you want)
TRAEFIK_1_URL=http://localhost:8080
TRAEFIK_1_GROUP=Local Server

TRAEFIK_2_URL=http://traefik-prod.example.com:8080
TRAEFIK_2_GROUP=Production

TRAEFIK_3_URL=http://traefik-staging.example.com:8080
TRAEFIK_3_GROUP=Staging

# Docker Servers (you can add as many as you want)
# Docker host in Uptime Kuma will be: {GROUP}-docker
DOCKER_1_URL=tcp://docker-proxy-local:2375
DOCKER_1_GROUP=Local

DOCKER_2_URL=tcp://10.200.200.2:2375
DOCKER_2_GROUP=hal-wg

DOCKER_3_URL=tcp://10.200.200.3:2375
DOCKER_3_GROUP=plague-wg

# Ignore Patterns
IGNORE_PATTERNS=*redis*,*traefik*,*internal*
```

### Docker Host Configuration

When you configure a Docker server with `DOCKER_1_GROUP=Local`, the script will:
1. Fetch all running containers from the Docker API at `DOCKER_1_URL`
2. Create a Docker container monitor for each container
3. Set the monitor's Docker host to `Local-docker`
4. Add two tags to each monitor: "docker" and "Local"

**Important**: Before monitors can work, you must configure the Docker host in Uptime Kuma:
1. Go to Settings → Docker Hosts
2. Add a new Docker host with name `{GROUP}-docker` (e.g., `Local-docker`)
3. Set the Docker daemon URL to the same value as in your `.env` file (e.g., `tcp://docker-proxy-local:2375`)

For the example configuration above, you would create three Docker hosts in Uptime Kuma:
- Name: `Local-docker`, URL: `tcp://docker-proxy-local:2375`
- Name: `hal-wg-docker`, URL: `tcp://10.200.200.2:2375`
- Name: `plague-wg-docker`, URL: `tcp://10.200.200.3:2375`

```

### Ignore Patterns

You can specify patterns to exclude certain hosts from monitoring. Hosts matching these patterns will:
- **Not have monitors created** for them
- **Have existing monitors removed** if they match

Patterns support wildcards (`*`) using standard shell-style pattern matching:

```bash
# Examples:
IGNORE_PATTERNS=*redis*,*traefik*,test.example.com,*.internal.com

# This will ignore:
# - Any host containing "redis" (e.g., redis-1.example.com, my-redis.example.com)
# - Any host containing "traefik" (e.g., traefik.example.com)
# - Exact match: test.example.com
# - Any subdomain of internal.com (e.g., api.internal.com, web.internal.com)
```

Common use cases:
- `*redis*` - Skip Redis admin interfaces
- `*traefik*` - Skip Traefik dashboard
- `*postgres*` - Skip PostgreSQL admin tools
- `*-internal` - Skip services ending with "-internal"

### Tag Management

The script automatically manages tags/groups for your monitors:

- **Creates tags** if they don't exist (using the `TRAEFIK_X_GROUP` name)
- **Verifies existing monitors** have the correct tag for their Traefik source
- **Adds missing tags** to monitors that should have them but don't
- **Preserves existing tags** - monitors can have multiple tags, so this only adds the required tag without removing others

This ensures that if you change a group name or manually remove tags, running the sync will restore them correctly.

#### Reset Tags Mode

If your monitors have accumulated incorrect or old tags over time, you can enable reset mode:

```bash
# In .env file
RESET_TAGS=true
```

When enabled, the script will:
1. **Remove ALL existing tags** from each monitor
2. **Add only the correct group tag** for that monitor's Traefik source

This is useful for cleaning up after:
- Changing group names
- Manual tag modifications
- Migration from another monitoring system
- Accumulated test/old tags

**Important Notes**:
- After running once with `RESET_TAGS=true`, set it back to `false` to return to normal additive behavior
- The script automatically detects and recovers from session timeouts by re-authenticating
- A 0.2 second delay is added between operations to reduce API load

## Usage

### Running from Docker (Recommended)

```bash
# Enter the container
docker exec -it auto-monitor bash

# Run the sync
uv run sync_monitors.py
```

### Running Locally

```bash
# From the auto-monitor directory
uv run sync_monitors.py
```

The script will:
1. Connect to all configured Traefik instances
2. Extract all HTTPS host rules
3. Connect to Uptime Kuma
4. Remove monitors matching ignore patterns (if configured)
5. Create or find tags for each Traefik group
6. Check existing monitors and add missing tags
7. Create monitors for any hosts that don't already exist
8. Assign the appropriate tag to each monitor

### Command Line Options

You can override `.env` settings via command line:

```bash
# Specify custom .env file location
uv run sync_monitors.py --env-file /path/to/.env

# Override credentials
uv run sync_monitors.py --username admin --password mypass

# Override Uptime Kuma URL
uv run sync_monitors.py --uptime-url https://uptime.example.com
```

### Output

```
Loading configuration from .env...

Configuration:
  Uptime Kuma: https://uptime.example.com
  Traefik Servers: 2
    1. http://localhost:8080 (Group: Local Server)
    2. http://traefik-prod.example.com:8080 (Group: Production)

Connecting to Uptime Kuma...
Connected to Uptime Kuma
Authenticating as admin...
Authentication successful!
Fetching existing monitors...

Found 5 existing monitors

============================================================
Processing Traefik: http://localhost:8080
Group: Local Server
============================================================
Found 21 HTTPS hosts
Getting/creating tag for group 'Local Server'...
  Created new tag 'Local Server' (ID: 1)

Checking tags for existing monitors...
  Adding tag to: api.example.com
    ✓ Tag added
  Adding tag to: web.example.com
    ✓ Tag added
  Updated tags for 2 monitor(s)

Need to create 19 new monitors
Creating monitor for https://example.com...
  ✓ Created monitor (ID: 123)
...

============================================================
Sync complete! Created 19 new monitors.
============================================================
```

#### Example Output (Reset Tags Mode)

When `RESET_TAGS=true`:

```
Configuration:
  Uptime Kuma: https://uptime.example.com
  Traefik Servers: 1
    1. http://localhost:8080 (Group: Production)
  Reset Tags: ENABLED (will clear and reset all tags)

...

Resetting tags for existing monitors...
  Resetting tags for: api.example.com
    ✓ Tags reset (removed 2, added 1)
  Resetting tags for: web.example.com
    ✓ Tags reset (removed 3, added 1)
  Reset tags for 2 monitor(s)
```

## Monitor Settings

Each monitor is created with the following defaults:
- **Type**: HTTP(s)
- **Method**: GET
- **Interval**: 60 seconds
- **Retry Interval**: 60 seconds
- **Max Retries**: 0
- **Timeout**: 48 seconds
- **Accepted Status Codes**: 200-299
- **Max Redirects**: 10

You can modify these defaults in the `sync_monitors.py` file.

## Troubleshooting

### Authentication Failed
- Verify your username and password in `.env`
- Check that Uptime Kuma is accessible at the configured URL

### No Hosts Found
- Verify Traefik is accessible at the configured URL
- Check that Traefik has HTTPS routes configured
- Ensure the Traefik API is enabled

### Connection Issues
- Make sure websocket-client is installed (should be automatic with uv)
- Check firewall rules and network connectivity
- Verify SSL certificates if using HTTPS

## Development

Dependencies are managed via `pyproject.toml`:
- requests
- python-socketio
- websocket-client
- python-dotenv

To add dependencies:
```bash
# Edit pyproject.toml, then run:
uv sync
```

## License

MIT
