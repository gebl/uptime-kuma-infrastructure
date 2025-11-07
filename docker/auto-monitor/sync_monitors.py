#!/usr/bin/env python3
"""
Sync Traefik host rules with Uptime Kuma monitors.
"""
import argparse
import sys
import os
import requests
import re
import time
from fnmatch import fnmatch
from urllib.parse import urlparse
from dotenv import load_dotenv
from uptime_kuma_api import UptimeKumaApi, MonitorType

def extract_hosts_from_traefik(traefik_url):
    """Fetch routers from Traefik API and extract unique HTTPS hosts."""
    try:
        response = requests.get(f"{traefik_url}/api/rawdata")
        response.raise_for_status()
        data = response.json()

        routers = data.get("routers", {})
        hosts = set()

        for router_name, router_config in routers.items():
            # Only process routers with HTTPS entry points
            if "https" in router_config.get("entryPoints", []):
                rule = router_config.get("rule", "")
                # Extract host from rule like "Host(`example.com`)"
                match = re.search(r"Host\(`([^`]+)`\)", rule)
                if match:
                    hostname = match.group(1)
                    hosts.add(f"https://{hostname}")

        return sorted(hosts)
    except Exception as e:
        print(f"Error fetching Traefik data from {traefik_url}: {e}")
        return []

def extract_containers_from_docker(docker_url):
    """Fetch running containers from Docker API."""
    try:
        # Docker URL format: tcp://host:port or http://host:port
        # Convert tcp:// to http:// for requests library
        api_url = docker_url.replace('tcp://', 'http://')

        response = requests.get(f"{api_url}/containers/json")
        response.raise_for_status()
        containers = response.json()

        # Extract container names
        container_names = []
        for container in containers:
            names = container.get("Names", [])
            if names:
                # Docker API returns names with leading slash, remove it
                name = names[0].lstrip('/')
                container_names.append(name)

        return sorted(container_names)
    except Exception as e:
        print(f"Error fetching Docker data from {docker_url}: {e}")
        return []

def get_uptime_credentials(username=None, password=None):
    """Get or prompt for Uptime Kuma credentials."""
    if not username:
        username = input("Uptime Kuma username: ")
    if not password:
        password = input("Uptime Kuma password: ")
    return username, password

def should_ignore(url, ignore_patterns):
    """Check if a URL matches any ignore pattern."""
    if not ignore_patterns:
        return False

    # Extract hostname from URL
    hostname = urlparse(url).netloc if url.startswith(('http://', 'https://')) else url

    for pattern in ignore_patterns:
        pattern = pattern.strip()
        if not pattern:
            continue

        # Check if pattern matches the hostname or full URL
        if fnmatch(hostname.lower(), pattern.lower()) or fnmatch(url.lower(), pattern.lower()):
            return True

    return False

def get_or_create_tag(api, tag_name, ensure_auth_fn=None):
    """Get existing tag ID or create a new tag."""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # Get all tags
            tags = api.get_tags()

            # Check if tag exists
            for tag in tags:
                if tag.get("name") == tag_name:
                    return tag.get("id")

            # Create new tag
            new_tag = api.add_tag(name=tag_name, color="#4299e1")
            tag_id = new_tag.get("id")
            print(f"  Created new tag '{tag_name}' (ID: {tag_id})")
            return tag_id
        except Exception as e:
            error_msg = str(e).lower()
            if "not logged in" in error_msg or "unauthorized" in error_msg:
                if attempt < max_retries - 1 and ensure_auth_fn:
                    ensure_auth_fn()
                    continue  # Retry
            print(f"  Warning: Could not create tag '{tag_name}': {e}")
            return None

def get_docker_host_id(api, docker_host_name, ensure_auth_fn=None):
    """Get Docker host ID by name."""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            docker_hosts = api.get_docker_hosts()
            for host in docker_hosts:
                if host.get("name") == docker_host_name:
                    return host.get("id")
            print(f"  Warning: Docker host '{docker_host_name}' not found in Uptime Kuma")
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if "not logged in" in error_msg or "unauthorized" in error_msg:
                if attempt < max_retries - 1 and ensure_auth_fn:
                    ensure_auth_fn()
                    continue  # Retry
            print(f"  Warning: Could not get Docker hosts: {e}")
            return None

def add_tags_to_monitor(api, monitor_id, tag_ids, ensure_auth_fn=None):
    """Add multiple tags to a monitor with retry logic."""
    for tag_id in tag_ids:
        if not tag_id:
            continue
        max_retries = 2
        for attempt in range(max_retries):
            try:
                api.add_monitor_tag(tag_id=tag_id, monitor_id=monitor_id, value="")
                break  # Success
            except Exception as e:
                error_msg = str(e).lower()
                if "not logged in" in error_msg or "unauthorized" in error_msg:
                    if attempt < max_retries - 1 and ensure_auth_fn:
                        ensure_auth_fn()
                        continue  # Retry
                if attempt == max_retries - 1:
                    print(f"    Warning: Could not add tag (ID: {tag_id}): {e}")
                break

def sync_monitors(uptime_url, traefik_servers, docker_servers, username, password, ignore_patterns=None, reset_tags=False):
    """Connect to Uptime Kuma and create monitors for missing hosts from all Traefik servers and Docker containers."""

    api = UptimeKumaApi(uptime_url)

    def ensure_authenticated():
        """Ensure the API session is authenticated, re-login if needed."""
        print(f"\n  ⚠ Session expired, attempting to re-authenticate...")

        # Small delay before retrying
        time.sleep(1)

        try:
            # Try to disconnect cleanly
            api.disconnect()
            time.sleep(0.5)
        except Exception as e:
            print(f"  Note: Disconnect had issues (may be expected): {e}")

        try:
            # Reconnect Socket.io
            print(f"  • Reconnecting to {uptime_url}...")
            api.sio.connect(uptime_url, wait_timeout=10)

            # Re-authenticate
            print(f"  • Logging in as {username}...")
            api.login(username, password)
            print(f"  ✓ Re-authenticated successfully\n")
        except Exception as e:
            print(f"\n  ✗ Re-authentication failed")
            print(f"     Error type: {type(e).__name__}")
            print(f"     Error details: {str(e) or repr(e)}")
            print(f"\n  Possible causes:")
            print(f"     • Uptime Kuma server is rate-limiting connections")
            print(f"     • Network connectivity issues")
            print(f"     • Server is under heavy load")
            print(f"     • Session management issue in Uptime Kuma")
            print(f"\n  Suggestion: Wait 30-60 seconds, then run the script again to continue from where it left off.")
            print(f"  The script is idempotent - it will skip already-processed monitors.\n")
            sys.exit(1)

    try:
        print(f"Connecting to Uptime Kuma at {uptime_url}...")

        # Authenticate
        print(f"Authenticating as {username}...")
        api.login(username, password)
        print("Authentication successful!")

        # Get existing monitors
        print("Fetching existing monitors...")
        monitors = api.get_monitors()

        # Display ignore patterns if configured
        if ignore_patterns:
            print(f"\nIgnore patterns configured: {', '.join(ignore_patterns)}")

        # Remove monitors matching ignore patterns
        total_removed = 0
        if ignore_patterns:
            print("\nChecking for monitors to remove (matching ignore patterns)...")
            monitors_to_remove = []

            for monitor in monitors:
                url = monitor.get("url", "")
                monitor_id = monitor.get("id")
                monitor_name = monitor.get("name", "")

                if url and should_ignore(url, ignore_patterns):
                    monitors_to_remove.append((monitor_id, monitor_name, url))

            if monitors_to_remove:
                print(f"  Found {len(monitors_to_remove)} monitor(s) to remove:")
                for monitor_id, monitor_name, url in monitors_to_remove:
                    print(f"    • {monitor_name} ({url})")
                    try:
                        api.delete_monitor(monitor_id)
                        print(f"      ✓ Removed (ID: {monitor_id})")
                        total_removed += 1
                    except Exception as e:
                        print(f"      ✗ Failed: {e}")
                print(f"\n  Removed {total_removed} of {len(monitors_to_remove)} monitors")
                # Refresh monitor list after deletions
                monitors = api.get_monitors()
            else:
                print("  ✓ No monitors found matching ignore patterns")

        existing_urls = set()
        for monitor in monitors:
            url = monitor.get("url", "")
            if url:
                existing_urls.add(url)

        print(f"\nFound {len(existing_urls)} existing monitors")

        # Get or create the common "traefik" tag
        print(f"\nGetting/creating 'traefik' tag...")
        traefik_tag_id = get_or_create_tag(api, "traefik", ensure_authenticated)
        if not traefik_tag_id:
            print("Warning: Could not create 'traefik' tag, continuing without it")

        # Process each Traefik server
        total_created = 0
        for traefik_info in traefik_servers:
            traefik_url = traefik_info["url"]
            group_name = traefik_info["group"]

            print(f"\n{'='*60}")
            print(f"Processing Traefik: {traefik_url}")
            print(f"Group: {group_name}")
            print(f"{'='*60}")

            # Fetch hosts from this Traefik instance
            hosts = extract_hosts_from_traefik(traefik_url)
            if not hosts:
                print(f"  No hosts found or error occurred")
                continue

            print(f"Found {len(hosts)} HTTPS hosts")

            # Filter out ignored hosts
            if ignore_patterns:
                filtered_hosts = []
                ignored_count = 0
                for host in hosts:
                    if should_ignore(host, ignore_patterns):
                        ignored_count += 1
                    else:
                        filtered_hosts.append(host)
                hosts = filtered_hosts
                if ignored_count > 0:
                    print(f"  Ignored {ignored_count} hosts matching patterns")
                print(f"  {len(hosts)} hosts after filtering")

            # Get or create tag for this group
            tag_id = None
            if group_name:
                print(f"Getting/creating tag for group '{group_name}'...")
                tag_id = get_or_create_tag(api, group_name, ensure_authenticated)

            # Check and update tags for existing monitors
            if tag_id:
                if reset_tags:
                    print(f"\nResetting tags for existing monitors...")
                else:
                    print(f"\nChecking tags for existing monitors...")

                existing_hosts_for_this_traefik = [h for h in hosts if h in existing_urls]
                tags_updated = 0

                for host in existing_hosts_for_this_traefik:
                    # Find the monitor for this host
                    monitor_to_check = None
                    for monitor in monitors:
                        if monitor.get("url") == host:
                            monitor_to_check = monitor
                            break

                    if monitor_to_check:
                        monitor_id = monitor_to_check.get("id")
                        monitor_name = monitor_to_check.get("name")
                        monitor_tags = monitor_to_check.get("tags", [])

                        if reset_tags:
                            # Reset mode: remove all tags and add only the correct one
                            if len(monitor_tags) > 0:
                                print(f"  Resetting tags for: {monitor_name}")
                                # Remove all existing tags
                                failed = False
                                for tag in monitor_tags:
                                    max_retries = 2
                                    for attempt in range(max_retries):
                                        try:
                                            api.delete_monitor_tag(tag_id=tag.get("tag_id"), monitor_id=monitor_id, value=tag.get("value", ""))
                                            break  # Success
                                        except Exception as e:
                                            error_msg = str(e).lower()
                                            if "not logged in" in error_msg or "unauthorized" in error_msg:
                                                if attempt < max_retries - 1:
                                                    ensure_authenticated()
                                                    continue  # Retry
                                                else:
                                                    print(f"    ✗ Failed after re-authentication: {e}")
                                                    failed = True
                                                    break
                                            print(f"    Warning: Could not remove tag: {e}")
                                            failed = True
                                            break

                                # Add the correct tags (group + traefik)
                                if not failed:
                                    tags_to_add = [tag_id, traefik_tag_id]
                                    add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)
                                    num_tags_added = len([t for t in tags_to_add if t])
                                    print(f"    ✓ Tags reset (removed {len(monitor_tags)}, added {num_tags_added})")
                                    tags_updated += 1
                                    # Small delay to avoid overwhelming the API
                                    time.sleep(0.2)
                            else:
                                # No tags to remove, just add the correct tags
                                tags_to_add = [tag_id, traefik_tag_id]
                                add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)
                                print(f"  Added tags to: {monitor_name}")
                                tags_updated += 1
                                time.sleep(0.2)
                        else:
                            # Normal mode: check if correct tags exist and add if missing
                            has_group_tag = any(tag.get("tag_id") == tag_id for tag in monitor_tags)
                            has_traefik_tag = any(tag.get("tag_id") == traefik_tag_id for tag in monitor_tags)

                            tags_to_add = []
                            if not has_group_tag and tag_id:
                                tags_to_add.append(tag_id)
                            if not has_traefik_tag and traefik_tag_id:
                                tags_to_add.append(traefik_tag_id)

                            if tags_to_add:
                                print(f"  Adding tags to: {monitor_name}")
                                add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)
                                print(f"    ✓ {len(tags_to_add)} tag(s) added")
                                tags_updated += 1
                                time.sleep(0.2)

                if tags_updated > 0:
                    if reset_tags:
                        print(f"  Reset tags for {tags_updated} monitor(s)")
                    else:
                        print(f"  Updated tags for {tags_updated} monitor(s)")
                else:
                    if reset_tags:
                        print(f"  ✓ All monitors already have only the correct tag")
                    else:
                        print(f"  ✓ All existing monitors have correct tags")

            # Add missing monitors
            missing_hosts = [h for h in hosts if h not in existing_urls]
            print(f"\nNeed to create {len(missing_hosts)} new monitors")

            for host in missing_hosts:
                hostname = urlparse(host).netloc
                print(f"Creating monitor for {host}...")

                try:
                    # Prepare monitor configuration
                    monitor_config = {
                        "type": MonitorType.HTTP,
                        "name": hostname,
                        "url": host,
                        "method": "GET",
                        "interval": 60,
                        "retryInterval": 60,
                        "maxretries": 0,
                        "accepted_statuscodes": ["200-299"],
                        "maxredirects": 10,
                        "timeout": 48
                    }

                    # Add monitor
                    result = api.add_monitor(**monitor_config)
                    monitor_id = result.get("monitorID")

                    # Add tags if available (group + traefik)
                    if monitor_id:
                        tags_to_add = [tag_id, traefik_tag_id]
                        add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)

                    print(f"  ✓ Created monitor (ID: {monitor_id})")
                    total_created += 1
                    existing_urls.add(host)  # Add to existing URLs to avoid duplicates

                except Exception as e:
                    print(f"  ✗ Failed: {e}")

        # Process each Docker server
        for docker_info in docker_servers:
            docker_url = docker_info["url"]
            group_name = docker_info["group"]
            docker_host = f"{group_name}-docker"

            print(f"\n{'='*60}")
            print(f"Processing Docker: {docker_url}")
            print(f"Group: {group_name}")
            print(f"Docker Host: {docker_host}")
            print(f"{'='*60}")

            # Fetch containers from this Docker instance
            containers = extract_containers_from_docker(docker_url)
            if not containers:
                print(f"  No containers found or error occurred")
                continue

            print(f"Found {len(containers)} containers")

            # Get or create tag for this group
            tag_id = None
            if group_name:
                print(f"Getting/creating tag for group '{group_name}'...")
                tag_id = get_or_create_tag(api, group_name, ensure_authenticated)

            # Get or create the common "docker" tag
            print(f"Getting/creating 'docker' tag...")
            docker_tag_id = get_or_create_tag(api, "docker", ensure_authenticated)

            # Get Docker host ID
            print(f"Looking up Docker host ID for '{docker_host}'...")
            docker_host_id = get_docker_host_id(api, docker_host, ensure_authenticated)
            if not docker_host_id:
                print(f"  ✗ Docker host '{docker_host}' not found. Please configure it in Uptime Kuma Settings → Docker Hosts")
                continue

            # Check and update tags for existing monitors
            # For Docker monitors, we match on monitor name (container name) and docker_host
            if tag_id or docker_tag_id:
                if reset_tags:
                    print(f"\nResetting tags for existing Docker monitors...")
                else:
                    print(f"\nChecking tags for existing Docker monitors...")

                tags_updated = 0
                for container_name in containers:
                    # Find the monitor for this container
                    monitor_to_check = None
                    for monitor in monitors:
                        if (monitor.get("type") == MonitorType.DOCKER and
                            monitor.get("name") == container_name and
                            monitor.get("docker_host") == docker_host_id):
                            monitor_to_check = monitor
                            break

                    if monitor_to_check:
                        monitor_id = monitor_to_check.get("id")
                        monitor_name = monitor_to_check.get("name")
                        monitor_tags = monitor_to_check.get("tags", [])

                        if reset_tags:
                            # Reset mode: remove all tags and add only the correct ones
                            if len(monitor_tags) > 0:
                                print(f"  Resetting tags for: {monitor_name}")
                                # Remove all existing tags
                                failed = False
                                for tag in monitor_tags:
                                    max_retries = 2
                                    for attempt in range(max_retries):
                                        try:
                                            api.delete_monitor_tag(tag_id=tag.get("tag_id"), monitor_id=monitor_id, value=tag.get("value", ""))
                                            break  # Success
                                        except Exception as e:
                                            error_msg = str(e).lower()
                                            if "not logged in" in error_msg or "unauthorized" in error_msg:
                                                if attempt < max_retries - 1:
                                                    ensure_authenticated()
                                                    continue  # Retry
                                                else:
                                                    print(f"    ✗ Failed after re-authentication: {e}")
                                                    failed = True
                                                    break
                                            print(f"    Warning: Could not remove tag: {e}")
                                            failed = True
                                            break

                                # Add the correct tags (group + docker)
                                if not failed:
                                    tags_to_add = [tag_id, docker_tag_id]
                                    add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)
                                    num_tags_added = len([t for t in tags_to_add if t])
                                    print(f"    ✓ Tags reset (removed {len(monitor_tags)}, added {num_tags_added})")
                                    tags_updated += 1
                                    # Small delay to avoid overwhelming the API
                                    time.sleep(0.2)
                            else:
                                # No tags to remove, just add the correct tags
                                tags_to_add = [tag_id, docker_tag_id]
                                add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)
                                print(f"  Added tags to: {monitor_name}")
                                tags_updated += 1
                                time.sleep(0.2)
                        else:
                            # Normal mode: check if correct tags exist and add if missing
                            has_group_tag = any(tag.get("tag_id") == tag_id for tag in monitor_tags)
                            has_docker_tag = any(tag.get("tag_id") == docker_tag_id for tag in monitor_tags)

                            tags_to_add = []
                            if not has_group_tag and tag_id:
                                tags_to_add.append(tag_id)
                            if not has_docker_tag and docker_tag_id:
                                tags_to_add.append(docker_tag_id)

                            if tags_to_add:
                                print(f"  Adding tags to: {monitor_name}")
                                add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)
                                print(f"    ✓ {len(tags_to_add)} tag(s) added")
                                tags_updated += 1
                                time.sleep(0.2)

                if tags_updated > 0:
                    if reset_tags:
                        print(f"  Reset tags for {tags_updated} monitor(s)")
                    else:
                        print(f"  Updated tags for {tags_updated} monitor(s)")
                else:
                    if reset_tags:
                        print(f"  ✓ All monitors already have only the correct tags")
                    else:
                        print(f"  ✓ All existing monitors have correct tags")

            # Add missing Docker monitors
            existing_docker_monitors = set()
            for monitor in monitors:
                if (monitor.get("type") == MonitorType.DOCKER and
                    monitor.get("docker_host") == docker_host_id):
                    existing_docker_monitors.add(monitor.get("name"))

            missing_containers = [c for c in containers if c not in existing_docker_monitors]
            print(f"\nNeed to create {len(missing_containers)} new Docker monitors")

            for container_name in missing_containers:
                print(f"Creating Docker monitor for {container_name}...")

                try:
                    # Prepare monitor configuration
                    monitor_config = {
                        "type": MonitorType.DOCKER,
                        "name": container_name,
                        "docker_container": container_name,
                        "docker_host": docker_host_id
                    }

                    # Add monitor
                    result = api.add_monitor(**monitor_config)
                    monitor_id = result.get("monitorID")

                    # Add tags if available (group + docker)
                    if monitor_id:
                        tags_to_add = [tag_id, docker_tag_id]
                        add_tags_to_monitor(api, monitor_id, tags_to_add, ensure_authenticated)

                    print(f"  ✓ Created Docker monitor (ID: {monitor_id})")
                    total_created += 1

                except Exception as e:
                    print(f"  ✗ Failed: {e}")

        print(f"\n{'='*60}")
        print(f"Sync complete! Created {total_created} new monitors.")
        print(f"{'='*60}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            api.disconnect()
        except:
            pass

def load_config_from_env():
    """Load configuration from .env file."""
    load_dotenv()

    config = {
        "uptime_url": os.getenv("UPTIME_KUMA_URL"),
        "username": os.getenv("UPTIME_KUMA_USERNAME"),
        "password": os.getenv("UPTIME_KUMA_PASSWORD"),
        "traefik_servers": [],
        "docker_servers": [],
        "ignore_patterns": []
    }

    # Load Traefik servers (TRAEFIK_1_URL, TRAEFIK_1_GROUP, etc.)
    i = 1
    while True:
        url = os.getenv(f"TRAEFIK_{i}_URL")
        if not url:
            break

        group = os.getenv(f"TRAEFIK_{i}_GROUP", f"Traefik {i}")
        config["traefik_servers"].append({"url": url, "group": group})
        i += 1

    # Load Docker servers (DOCKER_1_URL, DOCKER_1_GROUP, etc.)
    i = 1
    while True:
        url = os.getenv(f"DOCKER_{i}_URL")
        if not url:
            break

        group = os.getenv(f"DOCKER_{i}_GROUP", f"Docker {i}")
        config["docker_servers"].append({"url": url, "group": group})
        i += 1

    # Load ignore patterns (comma-separated)
    ignore_patterns_str = os.getenv("IGNORE_PATTERNS", "")
    if ignore_patterns_str:
        config["ignore_patterns"] = [p.strip() for p in ignore_patterns_str.split(",") if p.strip()]

    # Load reset tags option
    reset_tags_str = os.getenv("RESET_TAGS", "false").lower()
    config["reset_tags"] = reset_tags_str in ["true", "1", "yes"]

    return config

def main():
    parser = argparse.ArgumentParser(
        description="Sync Traefik host rules with Uptime Kuma monitors. "
                    "Configuration can be provided via .env file or command line arguments."
    )
    parser.add_argument(
        "--uptime-url",
        help="Uptime Kuma URL (e.g., https://uptime.example.com)"
    )
    parser.add_argument(
        "--username",
        help="Uptime Kuma username"
    )
    parser.add_argument(
        "--password",
        help="Uptime Kuma password"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)"
    )

    args = parser.parse_args()

    # Load from .env file
    if os.path.exists(args.env_file):
        print(f"Loading configuration from {args.env_file}...")
        config = load_config_from_env()
    else:
        config = {
            "uptime_url": None,
            "username": None,
            "password": None,
            "traefik_servers": [],
            "docker_servers": [],
            "ignore_patterns": [],
            "reset_tags": False
        }

    # Command line args override .env
    uptime_url = args.uptime_url or config["uptime_url"]
    username = args.username or config["username"]
    password = args.password or config["password"]
    traefik_servers = config["traefik_servers"]
    docker_servers = config.get("docker_servers", [])
    ignore_patterns = config.get("ignore_patterns", [])
    reset_tags = config.get("reset_tags", False)

    # Validate required config
    if not uptime_url:
        print("Error: Uptime Kuma URL is required (via --uptime-url or UPTIME_KUMA_URL in .env)")
        sys.exit(1)

    if not traefik_servers and not docker_servers:
        print("Error: At least one Traefik or Docker server must be configured in .env file")
        print("Expected format: TRAEFIK_1_URL=http://... and TRAEFIK_1_GROUP=...")
        print("              or DOCKER_1_URL=tcp://... and DOCKER_1_GROUP=...")
        sys.exit(1)

    # Get credentials
    username, password = get_uptime_credentials(username, password)

    print(f"\nConfiguration:")
    print(f"  Uptime Kuma: {uptime_url}")
    if traefik_servers:
        print(f"  Traefik Servers: {len(traefik_servers)}")
        for i, server in enumerate(traefik_servers, 1):
            print(f"    {i}. {server['url']} (Group: {server['group']})")
    if docker_servers:
        print(f"  Docker Servers: {len(docker_servers)}")
        for i, server in enumerate(docker_servers, 1):
            print(f"    {i}. {server['url']} (Group: {server['group']})")
    if ignore_patterns:
        print(f"  Ignore Patterns: {', '.join(ignore_patterns)}")
    if reset_tags:
        print(f"  Reset Tags: ENABLED (will clear and reset all tags)")
    print()

    # Sync monitors
    sync_monitors(uptime_url, traefik_servers, docker_servers, username, password, ignore_patterns, reset_tags)

if __name__ == "__main__":
    main()
