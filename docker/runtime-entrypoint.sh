#!/bin/bash
set -e

# Function to determine the appropriate Java version based on server type and version
select_java_version() {
    local server_type="$1"
    local version="$2"
    
    # Default to Java 17
    local java_version="21"
    
    case "$server_type" in
        "vanilla"|"paper"|"purpur")
            # For newer versions (1.17+), use Java 17
            # For older versions (1.8-1.16), use Java 8
            if [[ "$version" == 1.8* ]] || [[ "$version" == 1.9* ]] || [[ "$version" == 1.10* ]] || [[ "$version" == 1.11* ]] || [[ "$version" == 1.12* ]] || [[ "$version" == 1.13* ]] || [[ "$version" == 1.14* ]] || [[ "$version" == 1.15* ]] || [[ "$version" == 1.16* ]]; then
                java_version="8"
            elif [[ "$version" == 1.17* ]] || [[ "$version" == 1.18* ]]; then
                java_version="17"
            elif [[ "$version" == 1.19* ]] || [[ "$version" == 1.20* ]] || [[ "$version" == 1.21* ]]; then
                java_version="21"
            fi
            ;;
        "fabric")
            # Fabric 1.19+ requires Java 17+
            # Older versions can use Java 8+
            if [[ "$version" == 1.19* ]] || [[ "$version" == 1.20* ]] || [[ "$version" == 1.21* ]]; then
                java_version="21"
            else
                java_version="8"
            fi
            ;;
        "forge"|"neoforge")
            # Forge 1.12 requires Java 8
            # Newer versions require Java 17+
            if [[ "$version" == 1.8* ]] || [[ "$version" == 1.9* ]] || [[ "$version" == 1.10* ]] || [[ "$version" == 1.11* ]] || [[ "$version" == 1.12* ]]; then
                java_version="8"
            else
                java_version="17"
            fi
            ;;
    esac
    
    echo "$java_version"
}

# Get server type and version from environment or labels
SERVER_TYPE="${SERVER_TYPE:-}"
SERVER_VERSION="${SERVER_VERSION:-}"

# Get Java version from environment or labels
JAVA_VERSION="${JAVA_VERSION:-}"
JAVA_BIN="${JAVA_BIN:-}"
# Optional override for which jar to launch
SERVER_JAR="${SERVER_JAR:-}"

# If Java version not set in environment, select based on server type and version
if [ -z "$JAVA_VERSION" ]; then
    JAVA_VERSION=$(select_java_version "$SERVER_TYPE" "$SERVER_VERSION")
fi

# Set Java binary path if not already set
if [ -z "$JAVA_BIN" ]; then
    JAVA_BIN="/usr/local/bin/java${JAVA_VERSION}"
fi

echo "DEBUG: Server type: $SERVER_TYPE, version: $SERVER_VERSION"
echo "DEBUG: Selected Java version: $JAVA_VERSION"
echo "DEBUG: Java binary: $JAVA_BIN"

# Configure memory settings from environment variables
MIN_RAM="${MIN_RAM:-1G}"
MAX_RAM="${MAX_RAM:-2G}"
MEM_ARGS="-Xmx${MAX_RAM} -Xms${MIN_RAM}"
JAVA_OPTS="${JAVA_OPTS:-}"
ALL_JAVA_ARGS="$MEM_ARGS $JAVA_OPTS"

echo "DEBUG: Memory configuration - Min: $MIN_RAM, Max: $MAX_RAM"
echo "DEBUG: Java memory args: $MEM_ARGS"
echo "DEBUG: Extra Java opts: $JAVA_OPTS"

# Debug: Print environment and directory info
echo "DEBUG: SERVER_DIR_NAME=$SERVER_DIR_NAME"
echo "DEBUG: WORKDIR=$WORKDIR"
echo "DEBUG: Current directory before change: $(pwd)"
echo "DEBUG: /data/servers exists: $([ -d "/data/servers" ] && echo "yes" || echo "no")"
[ -d "/data/servers" ] && echo "DEBUG: /data/servers contents: $(ls -la /data/servers)"

# Use WORKDIR if set, otherwise fall back to SERVER_DIR_NAME or /data
if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
  cd "$WORKDIR"
  echo "DEBUG: Changed to WORKDIR: $(pwd)"
elif [ -n "$SERVER_DIR_NAME" ] && [ -d "/data/servers/$SERVER_DIR_NAME" ]; then
  cd "/data/servers/$SERVER_DIR_NAME"
  echo "DEBUG: Changed to /data/servers/$SERVER_DIR_NAME: $(pwd)"
elif [ -n "$SERVER_DIR_NAME" ] && [ -d "/data/$SERVER_DIR_NAME" ]; then
  cd "/data/$SERVER_DIR_NAME"
  echo "DEBUG: Changed to /data/$SERVER_DIR_NAME: $(pwd)"
else
  cd "/data"
  echo "DEBUG: Changed to /data: $(pwd)"
fi

# Run installer if present (forge/neoforge)
INSTALLER_JAR=$(ls *installer*.jar 2>/dev/null || true)
if [ -n "$INSTALLER_JAR" ]; then
  echo "Running installer: $INSTALLER_JAR"
  # Use --installServer (note the capital S) for headless installation
  "$JAVA_BIN" -jar "$INSTALLER_JAR" --installServer || {
    echo "Installer failed, trying alternative flags..." >&2
    # Some older Forge versions might use different flags
    "$JAVA_BIN" -jar "$INSTALLER_JAR" --install-server || {
      echo "Installer failed with both flags" >&2
      exit 1
    }
  }
  rm -f *installer*.jar || true
  
  # For NeoForge, the installer creates a JAR with a specific naming pattern
  # Look for the generated server JAR
  echo "DEBUG: Looking for generated server JAR after installer"
  echo "DEBUG: Current directory contents after installer: $(ls -la)"
  
  # NeoForge creates JARs like: neoforge-{version}-universal.jar
  NEOFORGE_JAR=$(ls neoforge-*-universal.jar 2>/dev/null | head -n 1)
  if [ -n "$NEOFORGE_JAR" ]; then
    echo "DEBUG: Found NeoForge JAR: $NEOFORGE_JAR"
    # Rename to server.jar for consistency
    mv "$NEOFORGE_JAR" server.jar
    echo "DEBUG: Renamed $NEOFORGE_JAR to server.jar"
  fi
fi

# If EULA missing, accept
if [ ! -f eula.txt ]; then
  echo "eula=true" > eula.txt
fi

# Preferred jars/patterns
echo "DEBUG: Searching for server jars in $(pwd)"
echo "DEBUG: Current directory contents: $(ls -la)"
start_jar=""

# Prefer explicit SERVER_JAR if set and exists
if [ -n "$SERVER_JAR" ]; then
  if [ -f "$SERVER_JAR" ]; then
    start_jar="$SERVER_JAR"
    echo "DEBUG: Using SERVER_JAR specified: $start_jar"
  elif [ -f "./$SERVER_JAR" ]; then
    start_jar="./$SERVER_JAR"
    echo "DEBUG: Using SERVER_JAR specified (relative): $start_jar"
  else
    echo "WARNING: SERVER_JAR '$SERVER_JAR' not found; falling back to autodetection"
  fi
fi

# Check for specific JAR patterns in order of preference
if [ -z "$start_jar" ]; then
  for pattern in "server.jar" "neoforge-*-universal.jar" "*forge-*-universal.jar" "forge-*-server.jar" "*paper*.jar" "*purpur*.jar" "*fabric*.jar" "*server*.jar"; do
    echo "DEBUG: Checking pattern: $pattern"
    found=$(ls $pattern 2>/dev/null | head -n 1 || true)
    if [ -n "$found" ]; then
      start_jar="$found"
      echo "DEBUG: Found jar: $start_jar"
      break
    fi
  done
fi

# Fallback: look inside /data/servers/* for a jar
if [ -z "$start_jar" ] && [ -d "/data/servers" ]; then
  alt_jar=$(find /data/servers -maxdepth 2 -type f \( -name 'server.jar' -o -name 'neoforge-*-universal.jar' -o -name '*forge-*-universal.jar' -o -name 'forge-*-server.jar' -o -name '*paper*.jar' -o -name '*purpur*.jar' -o -name '*fabric*.jar' -o -name '*server*.jar' \) | head -n 1)
  if [ -n "$alt_jar" ]; then
    WORKDIR_BASE=$(dirname "$alt_jar")
    cd "$WORKDIR_BASE"
    start_jar=$(basename "$alt_jar")
  fi
fi

# Handle Fabric servers specially
if [ "$SERVER_TYPE" = "fabric" ] && [ -n "$start_jar" ]; then
  echo "Handling Fabric server"
  
  # Validate JAR file before starting
  if [ ! -f "$start_jar" ]; then
    echo "ERROR: JAR file $start_jar not found!" >&2
    exit 1
  fi
  
  jar_size=$(stat -c%s "$start_jar" 2>/dev/null || stat -f%z "$start_jar" 2>/dev/null || echo "0")
  echo "DEBUG: Fabric JAR file size: $jar_size bytes"
  
  # Check if JAR is too small (likely corrupted)
  min_size=5000  # 5KB minimum for Fabric launcher JARs
  if [ "$jar_size" -lt $min_size ]; then
    echo "ERROR: Fabric JAR file $start_jar is too small ($jar_size bytes), likely corrupted!" >&2
    echo "ERROR: Expected at least ${min_size} bytes for a valid Fabric launcher JAR" >&2
    exit 1
  fi
  
  # If the chosen jar filename contains 'fabric', assume it's the launcher and use 'server' argument; otherwise, run normally (nogui)
  if echo "$start_jar" | grep -qi "fabric"; then
    echo "Starting Fabric via launcher: $start_jar (with 'server' argument)"
    exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" server
  else
    echo "Starting Fabric using standard server jar: $start_jar (nogui)"
    exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" nogui
  fi
fi

# If run script exists, prefer it
if [ -z "$start_jar" ] && [ -f run.sh ]; then
  echo "Starting via run.sh"
  exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar server.jar server
fi

# For other server types
if [ -n "$start_jar" ]; then
  echo "Starting server in $(pwd): $start_jar"
  
  # Validate JAR file before starting
  if [ ! -f "$start_jar" ]; then
    echo "ERROR: JAR file $start_jar not found!" >&2
    exit 1
  fi
  
  jar_size=$(stat -c%s "$start_jar" 2>/dev/null || stat -f%z "$start_jar" 2>/dev/null || echo "0")
  echo "DEBUG: JAR file size: $jar_size bytes"
  
  # Check if JAR is too small (likely corrupted)
  min_size=50000  # 50KB minimum for general servers
  
  if [ "$jar_size" -lt $min_size ]; then
    echo "ERROR: JAR file $start_jar is too small ($jar_size bytes), likely corrupted!" >&2
    echo "ERROR: Expected at least ${min_size} bytes for a valid Minecraft server JAR" >&2
    exit 1
  fi
  
  # Test JAR file integrity
  if ! "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" --help >/dev/null 2>&1; then
    echo "WARNING: JAR file validation failed, but attempting to start anyway..."
  fi
  
  exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" nogui
fi

echo "No server jar or run.sh found in $(pwd). Contents:" >&2
ls -la >&2
[ -d /data/servers ] && echo "Index of /data/servers:" >&2 && ls -la /data/servers >&2
[ -n "$SERVER_DIR_NAME" ] && [ -d "/data/servers/$SERVER_DIR_NAME" ] && echo "Index of /data/servers/$SERVER_DIR_NAME:" >&2 && ls -la "/data/servers/$SERVER_DIR_NAME" >&2
exit 1