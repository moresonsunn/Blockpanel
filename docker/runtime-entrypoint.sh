#!/bin/bash
set -e

# Function to determine the appropriate Java version based on server type and version
select_java_version() {
    local server_type="$1"
    local version="$2"
    
    # Default to Java 21 (modern, LTS; compatible with most recent servers)
  local java_version="21"
  echo "DEBUG: select_java_version: type='${server_type}', version='${version}'" >&2
    
    case "$server_type" in
    "vanilla"|"paper"|"purpur")
      # For 1.8-1.16 -> Java 8; 1.17-1.18 -> Java 17; 1.19+ -> Java 21
            if [[ "$version" == 1.8* ]] || [[ "$version" == 1.9* ]] || [[ "$version" == 1.10* ]] || [[ "$version" == 1.11* ]] || [[ "$version" == 1.12* ]] || [[ "$version" == 1.13* ]] || [[ "$version" == 1.14* ]] || [[ "$version" == 1.15* ]] || [[ "$version" == 1.16* ]]; then
                echo "DEBUG: select_java_version: vanilla/paper/purpur matched 1.8-1.16 -> Java 8" >&2
                java_version="8"
            elif [[ "$version" == 1.17* ]] || [[ "$version" == 1.18* ]]; then
                echo "DEBUG: select_java_version: vanilla/paper/purpur matched 1.17-1.18 -> Java 17" >&2
                java_version="17"
            elif [[ "$version" == 1.19* ]] || [[ "$version" == 1.20* ]] || [[ "$version" == 1.21* ]]; then
                echo "DEBUG: select_java_version: vanilla/paper/purpur matched 1.19+ -> Java 21" >&2
                java_version="21"
            else
                echo "DEBUG: select_java_version: vanilla/paper/purpur no explicit match; keeping default ${java_version}" >&2
            fi
            ;;
  "fabric"|"quilt")
      # Fabric/Quilt: 1.8-1.16 -> Java 8; 1.17-1.18 -> Java 17; 1.19+ -> Java 21
      if [[ "$version" == 1.19* ]] || [[ "$version" == 1.20* ]] || [[ "$version" == 1.21* ]]; then
  echo "DEBUG: select_java_version: fabric/quilt matched 1.19+ -> Java 21" >&2
        java_version="21"
      elif [[ "$version" == 1.17* ]] || [[ "$version" == 1.18* ]]; then
  echo "DEBUG: select_java_version: fabric/quilt matched 1.17-1.18 -> Java 17" >&2
        java_version="17"
      else
  echo "DEBUG: select_java_version: fabric/quilt matched <=1.16 -> Java 8" >&2
        java_version="8"
      fi
      ;;
  "forge"|"neoforge")
      # Forge/NeoForge: <=1.12 -> Java 8; 1.13-1.20.4 -> Java 17; 1.20.5+/1.21+ -> Java 21
      if [[ "$version" == 1.8* ]] || [[ "$version" == 1.9* ]] || [[ "$version" == 1.10* ]] || [[ "$version" == 1.11* ]] || [[ "$version" == 1.12* ]]; then
                echo "DEBUG: select_java_version: forge/neoforge matched <=1.12 -> Java 8" >&2
                java_version="8"
      elif [[ "$version" == 1.20.5* ]] || [[ "$version" == 1.20.6* ]] || [[ "$version" == 1.21* ]]; then
  echo "DEBUG: select_java_version: forge/neoforge matched 1.20.5+/1.21+ -> Java 21" >&2
        java_version="21"
            else
                echo "DEBUG: select_java_version: forge/neoforge matched 1.13-1.20.4 -> Java 17" >&2
                java_version="17"
            fi
            ;;
    esac
    
    echo "$java_version"
}

# Get server type and version from environment or labels
SERVER_TYPE="${SERVER_TYPE:-}"
SERVER_VERSION="${SERVER_VERSION:-}"

# Get Java version override and JAVA_BIN override from environment
JAVA_VERSION_OVERRIDE="${JAVA_VERSION_OVERRIDE:-}"
JAVA_BIN_OVERRIDE="${JAVA_BIN_OVERRIDE:-}"
# Optional override for which jar to launch
SERVER_JAR="${SERVER_JAR:-}"

# Compute JAVA_VERSION from server type/version unless explicitly overridden
JAVA_VERSION=$(select_java_version "$SERVER_TYPE" "$SERVER_VERSION")
if [ -n "$JAVA_VERSION_OVERRIDE" ]; then
  echo "DEBUG: Overriding selected Java version with JAVA_VERSION_OVERRIDE=$JAVA_VERSION_OVERRIDE"
  JAVA_VERSION="$JAVA_VERSION_OVERRIDE"
fi
export JAVA_VERSION

# Set Java binary path: prefer explicit override, else pick by JAVA_VERSION
if [ -n "$JAVA_BIN_OVERRIDE" ]; then
  JAVA_BIN="$JAVA_BIN_OVERRIDE"
else
  JAVA_BIN="/usr/local/bin/java${JAVA_VERSION}"
fi

# Fallback if the desired JAVA_BIN doesn't exist or isn't executable
if [ ! -x "$JAVA_BIN" ]; then
  if command -v "java${JAVA_VERSION}" >/dev/null 2>&1; then
    JAVA_BIN="$(command -v "java${JAVA_VERSION}")"
    echo "DEBUG: Falling back to discovered java${JAVA_VERSION} at: $JAVA_BIN"
  elif command -v java >/dev/null 2>&1; then
    JAVA_BIN="$(command -v java)"
    echo "DEBUG: Falling back to system java at: $JAVA_BIN"
  else
    echo "ERROR: No suitable Java found for version ${JAVA_VERSION}" >&2
    exit 1
  fi
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

# -------- Incompatible-loader & client-only purge --------
AUTO_CLIENT_PURGE=${AUTO_CLIENT_PURGE:-1}
AUTO_INCOMPATIBLE_PURGE=${AUTO_INCOMPATIBLE_PURGE:-1}

have_unzip() { command -v unzip >/dev/null 2>&1; }
have_curl() { command -v curl >/dev/null 2>&1; }

load_extra_patterns() {
  # Sources: env var, optional URL, optional files (one pattern per line). All lowercased.
  local out=()
  # env var: comma-separated
  if [ -n "${CLIENT_ONLY_MOD_PATTERNS:-}" ]; then
    IFS=',' read -ra __tokarr <<< "${CLIENT_ONLY_MOD_PATTERNS}"
    for __tok in "${__tokarr[@]}"; do
      __tok="$(echo "$__tok" | tr '[:upper:]' '[:lower:]' | xargs)"
      [ -n "$__tok" ] && out+=("$__tok")
    done
  fi
  # URL: one per line, supports comments
  if [ -n "${CLIENT_ONLY_MOD_PATTERNS_URL:-}" ] && have_curl; then
    if curl -fsSL "$CLIENT_ONLY_MOD_PATTERNS_URL" -o /tmp/__client_only_list 2>/dev/null; then
      while IFS= read -r __line || [ -n "$__line" ]; do
        __line="$(echo "$__line" | tr '[:upper:]' '[:lower:]' | sed 's/^\s\+//;s/\s\+$//')"
        if [ -n "$__line" ] && ! echo "$__line" | grep -qE '^#'; then
          out+=("$__line")
        fi
      done < /tmp/__client_only_list
      rm -f /tmp/__client_only_list 2>/dev/null || true
    fi
  fi
  # Files
  for cfg in "./client-only-mods.txt" "/data/servers/client-only-mods.txt"; do
    if [ -f "$cfg" ]; then
      while IFS= read -r __line || [ -n "$__line" ]; do
        __line="$(echo "$__line" | tr '[:upper:]' '[:lower:]' | sed 's/^\s\+//;s/\s\+$//')"
        if [ -n "$__line" ] && ! echo "$__line" | grep -qE '^#'; then
          out+=("$__line")
        fi
      done < "$cfg"
    fi
  done
  printf '%s\n' "${out[@]}"
}

# Allowlist patterns for incompatible purge (never move if matched)
load_incompat_allowlist() {
  local out=()
  if [ -n "${INCOMPATIBLE_PURGE_ALLOWLIST:-}" ]; then
    IFS=',' read -ra __tokarr <<< "${INCOMPATIBLE_PURGE_ALLOWLIST}"
    for __tok in "${__tokarr[@]}"; do
      __tok="$(echo "$__tok" | tr '[:upper:]' '[:lower:]' | xargs)"
      [ -n "$__tok" ] && out+=("$__tok")
    done
  fi
  for cfg in "./incompatible-allowlist.txt" "/data/servers/incompatible-allowlist.txt"; do
    if [ -f "$cfg" ]; then
      while IFS= read -r __line || [ -n "$__line" ]; do
        __line="$(echo "$__line" | tr '[:upper:]' '[:lower:]' | sed 's/^\s\+//;s/\s\+$//')"
        if [ -n "$__line" ] && ! echo "$__line" | grep -qE '^#'; then
          out+=("$__line")
        fi
      done < "$cfg"
    fi
  done
  printf '%s\n' "${out[@]}"
}

# Force patterns: always treated as client-only, regardless of metadata
load_force_patterns() {
  local out=()
  if [ -n "${CLIENT_ONLY_FORCE_PATTERNS:-}" ]; then
    IFS=',' read -ra __tokarr <<< "${CLIENT_ONLY_FORCE_PATTERNS}"
    for __tok in "${__tokarr[@]}"; do
      __tok="$(echo "$__tok" | tr '[:upper:]' '[:lower:]' | xargs)"
      [ -n "$__tok" ] && out+=("$__tok")
    done
  fi
  for cfg in "./client-only-force.txt" "/data/servers/client-only-force.txt"; do
    if [ -f "$cfg" ]; then
      while IFS= read -r __line || [ -n "$__line" ]; do
        __line="$(echo "$__line" | tr '[:upper:]' '[:lower:]' | sed 's/^\s\+//;s/\s\+$//')"
        if [ -n "$__line" ] && ! echo "$__line" | grep -qE '^#'; then
          out+=("$__line")
        fi
      done < "$cfg"
    fi
  done
  printf '%s\n' "${out[@]}"
}

is_client_only_jar() {
  local jar="$1"
  local has_meta=0
  if have_unzip; then
    # Fabric
    if unzip -p "$jar" fabric.mod.json >/tmp/__fmj 2>/dev/null; then
      has_meta=1
      if grep -qi '"environment"[[:space:]]*:[[:space:]]*"client"' /tmp/__fmj; then
        rm -f /tmp/__fmj
        return 0
      fi
      rm -f /tmp/__fmj
    fi
    # Quilt
    if unzip -p "$jar" quilt.mod.json >/tmp/__qmj 2>/dev/null; then
      has_meta=1
      if grep -qi '"environment"[[:space:]]*:[[:space:]]*"client"' /tmp/__qmj; then
        rm -f /tmp/__qmj
        return 0
      fi
      rm -f /tmp/__qmj
    fi
    # Forge heuristic via mods.toml
    if unzip -p "$jar" META-INF/mods.toml >/tmp/__mt 2>/dev/null; then
      has_meta=1
      # Strict: only treat as client-only if explicit boolean flags are present
      if grep -Eiq '(clientsideonly|onlyclient|client_only)\s*=\s*true' /tmp/__mt; then
        rm -f /tmp/__mt
        return 0
      fi
      rm -f /tmp/__mt
    fi
  fi
  # Optional pattern fallback (from env/URL/files only)
  local base lower
  base="$(basename "$jar")"
  lower="${base,,}"
  if [ "$has_meta" -eq 0 ]; then
    while read -r pat; do
      [ -z "$pat" ] && continue
      [[ "$lower" == *"$pat"* ]] && return 0
    done < <(load_extra_patterns)
  fi
  # Force overrides: always apply
  while read -r fpat; do
    [ -z "$fpat" ] && continue
    [[ "$lower" == *"$fpat"* ]] && return 0
  done < <(load_force_patterns)
  return 1
}

detect_loader() {
  local jar="$1"
  local has_fabric=0
  local has_quilt=0
  local has_forge=0
  if have_unzip; then
    unzip -l "$jar" fabric.mod.json >/dev/null 2>&1 && has_fabric=1 || true
    unzip -l "$jar" quilt.mod.json  >/dev/null 2>&1 && has_quilt=1  || true
    unzip -l "$jar" META-INF/mods.toml >/dev/null 2>&1 && has_forge=1 || true
  fi
  if [ $has_forge -eq 1 ] && { [ $has_fabric -eq 1 ] || [ $has_quilt -eq 1 ]; }; then
    echo "both"
    return 0
  fi
  if [ $has_fabric -eq 1 ]; then echo "fabric"; return 0; fi
  if [ $has_quilt -eq 1 ]; then echo "quilt"; return 0; fi
  if [ $has_forge -eq 1 ]; then echo "forge"; return 0; fi
  echo ""
}

purge_mods() {
  local mods_dir="./mods"
  [ -d "$mods_dir" ] || return 0
  local disable_client_dir="./mods-disabled-client"
  local disable_incompat_dir="./mods-disabled-incompatible"
  mkdir -p "$disable_client_dir" "$disable_incompat_dir"
  local moved_client=0
  local moved_incompat=0
  shopt -s nullglob
  for f in "$mods_dir"/*.jar; do
    # First, purge incompatible loader jars based on SERVER_TYPE
    if [ "$AUTO_INCOMPATIBLE_PURGE" = "1" ]; then
      loader="$(detect_loader "$f")"
      base_name="$(basename "$f")"; lower_name="${base_name,,}"
      # Check allowlist first
      allow_match=0
      while read -r ap; do
        [ -z "$ap" ] && continue
        if [[ "$lower_name" == *"$ap"* ]]; then allow_match=1; break; fi
      done < <(load_incompat_allowlist)
      if [ "$allow_match" = "1" ]; then
        echo "INFO: Allowlisted from incompatible purge: $base_name"
        continue
      fi
      # Skip incompatible purge for multi-loader jars
      if [ "$loader" = "both" ]; then
        : # compatible with both ecosystems; do not move
      elif { [ "$SERVER_TYPE" = "forge" ] || [ "$SERVER_TYPE" = "neoforge" ]; } && { [ "$loader" = "fabric" ] || [ "$loader" = "quilt" ]; }; then
        echo "INFO: Disabling incompatible loader (Fabric/Quilt on Forge): $(basename "$f")"
        mv -f "$f" "$disable_incompat_dir"/ || true
        moved_incompat=$((moved_incompat+1))
        continue
      fi
      if { [ "$SERVER_TYPE" = "fabric" ] || [ "$SERVER_TYPE" = "quilt" ]; } && [ "$loader" = "forge" ]; then
        echo "INFO: Disabling incompatible loader (Forge on Fabric/Quilt): $(basename "$f")"
        mv -f "$f" "$disable_incompat_dir"/ || true
        moved_incompat=$((moved_incompat+1))
        continue
      fi
    fi

    # Then, purge known client-only jars conservatively
    if [ "$AUTO_CLIENT_PURGE" = "1" ] && is_client_only_jar "$f"; then
      echo "INFO: Disabling client-only mod: $(basename "$f")"
      mv -f "$f" "$disable_client_dir"/ || true
      moved_client=$((moved_client+1))
      continue
    fi
  done
  shopt -u nullglob
  [ "$moved_incompat" -gt 0 ] && echo "INFO: Moved $moved_incompat incompatible-loader mods to $disable_incompat_dir"
  [ "$moved_client" -gt 0 ] && echo "INFO: Moved $moved_client client-only mods to $disable_client_dir"
}

# Always run purge_mods (it respects the AUTO_* toggles internally)
purge_mods || true
# -------------------------------------------------------------------------

# Optionally disable problematic KubeJS datapacks referencing missing mods
AUTO_KUBEJS_PURGE=${AUTO_KUBEJS_PURGE:-1}

load_kubejs_disable_namespaces() {
  local out=()
  if [ -n "${KUBEJS_DISABLE_NAMESPACES:-}" ]; then
    IFS=',' read -ra __tokarr <<< "${KUBEJS_DISABLE_NAMESPACES}"
    for __tok in "${__tokarr[@]}"; do
      __tok="$(echo "$__tok" | tr '[:upper:]' '[:lower:]' | xargs)"
      [ -n "$__tok" ] && out+=("$__tok")
    done
  fi
  for cfg in "./kubejs-disable.txt" "./kubejs/kubejs-disable.txt"; do
    if [ -f "$cfg" ]; then
      while IFS= read -r __line || [ -n "$__line" ]; do
        __line="$(echo "$__line" | tr '[:upper:]' '[:lower:]' | sed 's/^\s\+//;s/\s\+$//')"
        if [ -n "$__line" ] && ! echo "$__line" | grep -qE '^#'; then
          out+=("$__line")
        fi
      done < "$cfg"
    fi
  done
  printf '%s\n' "${out[@]}"
}

disable_kubejs_namespace() {
  local ns="$1"
  local src="./kubejs/data/$ns"
  local dst="./kubejs/data.__disabled/$ns"
  if [ -d "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    echo "INFO: Disabling KubeJS datapack namespace: $ns"
    rm -rf "$dst" 2>/dev/null || true
    mv "$src" "$dst" || true
  fi
}

purge_kubejs_datapacks() {
  [ "$AUTO_KUBEJS_PURGE" = "1" ] || return 0
  [ -d ./kubejs/data ] || return 0
  # First, disable any namespaces explicitly provided via env/file
  while read -r ns; do
    [ -z "$ns" ] && continue
    disable_kubejs_namespace "$ns"
  done < <(load_kubejs_disable_namespaces)

  # Next, auto-disable namespaces whose backing mod isn't present
  # Heuristic: if no jar in ./mods (or disabled dirs) contains the namespace, move it out
  local mods_globs=("./mods" "./mods-disabled-client" "./mods-disabled-incompatible")
  for nsdir in ./kubejs/data/*; do
    [ -d "$nsdir" ] || continue
    ns="$(basename "$nsdir")"
    # Skip if already disabled explicitly above
    if [ -d "./kubejs/data.__disabled/$ns" ]; then
      continue
    fi
    # Check for any jar containing the namespace token
    local found=0
    for mg in "${mods_globs[@]}"; do
      [ -d "$mg" ] || continue
      if ls "$mg"/*"$ns"*.jar >/dev/null 2>&1; then
        found=1; break
      fi
    done
    if [ "$found" -eq 0 ]; then
      echo "INFO: KubeJS namespace '$ns' appears to target a missing mod; disabling"
      disable_kubejs_namespace "$ns"
    fi
  done
}

purge_kubejs_datapacks || true

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

# Remove stale session.lock if present (from prior crash)
cleanup_stale_session_lock() {
  local level_name="world"
  if [ -f server.properties ]; then
    # Extract level-name; keep everything after first '=' and trim CR
    local ln
    ln=$(grep -E '^level-name=' server.properties | sed -E 's/^level-name=//;s/\r$//')
    if [ -n "$ln" ]; then
      level_name="$ln"
    fi
  fi
  local wdir="./${level_name}"
  # Fallback if directory doesn't exist
  if [ ! -d "$wdir" ] && [ -d ./world ]; then
    wdir=./world
  fi
  if [ -f "$wdir/session.lock" ]; then
    # Log size for diagnostics
    local sz
    sz=$(stat -c%s "$wdir/session.lock" 2>/dev/null || stat -f%z "$wdir/session.lock" 2>/dev/null || echo "?")
    echo "DEBUG: Removing stale session.lock at $wdir/session.lock (size: $sz)"
    rm -f "$wdir/session.lock" || true
  fi
}

cleanup_stale_session_lock || true

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

# Check for specific JAR patterns in order of preference, tailored by server type
if [ -z "$start_jar" ]; then
  if [ "$SERVER_TYPE" = "forge" ] || [ "$SERVER_TYPE" = "neoforge" ]; then
    patterns="server.jar neoforge-*-universal.jar *forge-*-universal.jar forge-*-server.jar *server*.jar"
  elif [ "$SERVER_TYPE" = "fabric" ] || [ "$SERVER_TYPE" = "quilt" ]; then
    patterns="server.jar *fabric*.jar *quilt*.jar *server*.jar"
  else
    patterns="server.jar *paper*.jar *purpur*.jar *server*.jar"
  fi
  for pattern in $patterns; do
    echo "DEBUG: Checking pattern: $pattern"
    found=$(ls $pattern 2>/dev/null | head -n 1 || true)
    if [ -n "$found" ]; then
      start_jar="$found"
      echo "DEBUG: Found jar: $start_jar"
      break
    fi
  done
fi

# Removed cross-directory fallback search to avoid picking jars from other servers

# For Forge/NeoForge servers: if a jar exists, try running installer first headlessly
# For Forge/NeoForge: prefer run.sh immediately; do not try to 'install' non-installer jars
if { [ "$SERVER_TYPE" = "forge" ] || [ "$SERVER_TYPE" = "neoforge" ]; }; then
  if [ -f run.sh ]; then
    echo "Starting Forge/NeoForge via run.sh"
    chmod +x run.sh || true
    TMP_JAVA_DIR="/tmp/java-override"
    mkdir -p "$TMP_JAVA_DIR"
    ln -sf "$JAVA_BIN" "$TMP_JAVA_DIR/java"
    export PATH="$TMP_JAVA_DIR:$PATH"
    echo "DEBUG: Overriding 'java' for run.sh with: $JAVA_BIN"
    exec bash ./run.sh
  fi
fi

# Handle Fabric servers specially
if { [ "$SERVER_TYPE" = "fabric" ] || [ "$SERVER_TYPE" = "quilt" ]; } && [ -n "$start_jar" ]; then
  echo "Handling ${SERVER_TYPE^} server"
  
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
  
  # If the chosen jar filename contains 'fabric' or 'quilt', assume it's the launcher and use 'server' argument; otherwise, run normally (nogui)
  if echo "$start_jar" | grep -Eqi "fabric|quilt"; then
    echo "Starting ${SERVER_TYPE^} via launcher: $start_jar (with 'server' argument)"
  # Create stdin FIFO bridge to allow external commands
  mkfifo -m 600 console.in 2>/dev/null || true
  # Feed FIFO into Java stdin so the controller can write commands
  tail -f -n +1 console.in | exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" server
  else
    echo "Starting ${SERVER_TYPE^} using standard server jar: $start_jar (nogui)"
  mkfifo -m 600 console.in 2>/dev/null || true
  tail -f -n +1 console.in | exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" nogui
  fi
fi

# If run script exists, prefer it (execute script directly)
if [ -f run.sh ]; then
  echo "Starting via run.sh"
  chmod +x run.sh || true
  TMP_JAVA_DIR="/tmp/java-override"
  mkdir -p "$TMP_JAVA_DIR"
  ln -sf "$JAVA_BIN" "$TMP_JAVA_DIR/java"
  export PATH="$TMP_JAVA_DIR:$PATH"
  echo "DEBUG: Overriding 'java' for run.sh with: $JAVA_BIN"
  exec bash ./run.sh
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
  
  mkfifo -m 600 console.in 2>/dev/null || true
  tail -f -n +1 console.in | exec "$JAVA_BIN" $ALL_JAVA_ARGS -jar "$start_jar" nogui
fi

echo "No server jar or run.sh found in $(pwd). Contents:" >&2
ls -la >&2
[ -d /data/servers ] && echo "Index of /data/servers:" >&2 && ls -la /data/servers >&2
[ -n "$SERVER_DIR_NAME" ] && [ -d "/data/servers/$SERVER_DIR_NAME" ] && echo "Index of /data/servers/$SERVER_DIR_NAME:" >&2 && ls -la "/data/servers/$SERVER_DIR_NAME" >&2
exit 1