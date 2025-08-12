# Java Version Support Guide

This document explains the Java version support for different Minecraft server types and versions.

## Available Java Versions

The Docker runtime now includes all major Java versions:

- **Java 8** - For legacy Minecraft versions and older modpacks (Eclipse Temurin 8u392-b08)
- **Java 11** - For intermediate Minecraft versions (Eclipse Temurin 11.0.21+9)
- **Java 17** - For modern Minecraft versions (Eclipse Temurin 17.0.9+9)
- **Java 21** - For the latest Minecraft versions (OpenJDK 21 from base image)

## Automatic Java Version Selection

The system automatically selects the appropriate Java version based on:

1. **Server Type** (vanilla, paper, purpur, fabric, forge, neoforge)
2. **Minecraft Version** (1.8, 1.8.9, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20, 1.21)

## Java Version Mapping

### Vanilla, Paper, Purpur Servers

| Minecraft Version | Java Version | Reason |
|------------------|--------------|---------|
| 1.8 - 1.16 | Java 8 | Legacy compatibility |
| 1.17 - 1.18 | Java 17 | Minimum requirement |
| 1.19 - 1.21 | Java 21 | Latest performance |

### Fabric Servers

| Minecraft Version | Java Version | Reason |
|------------------|--------------|---------|
| 1.8 - 1.18 | Java 8 | Fabric loader compatibility |
| 1.19 - 1.21 | Java 21 | Latest Fabric features |

### Forge/NeoForge Servers

| Minecraft Version | Java Version | Reason |
|------------------|--------------|---------|
| 1.8 - 1.12 | Java 8 | Forge 1.12 requirement |
| 1.13+ | Java 17 | Modern Forge compatibility |

## Manual Java Version Override

You can manually override the Java version by setting environment variables:

```bash
# Set specific Java version
export JAVA_VERSION=8
export JAVA_BIN=/usr/local/bin/java8

# Or use the full path directly
export JAVA_BIN=/usr/local/bin/java21
```

## Testing Java Versions

Use the test script to verify all Java versions are working:

```bash
python test_docker_build.py
```

This will:
- Build the Docker image with all Java versions
- Test each Java version availability
- Verify binary paths and functionality
- Display version information

## Common Use Cases

### Legacy Modpacks (1.8.9, 1.12.2)
- **Recommended Java**: Java 8
- **Server Types**: Forge, Fabric
- **Examples**: FTB Legacy, older modpacks

### Modern Modpacks (1.16+)
- **Recommended Java**: Java 17
- **Server Types**: Forge, Fabric, Paper
- **Examples**: All the Mods, FTB Skies

### Latest Versions (1.19+)
- **Recommended Java**: Java 21
- **Server Types**: All server types
- **Examples**: Latest modpacks, vanilla servers

## Troubleshooting

### Java Version Issues

1. **"Invalid or corrupt jarfile" error**
   - Check if the correct Java version is being used
   - Verify the JAR file is complete and not corrupted

2. **"Unsupported major.minor version" error**
   - The Java version is too old for the server
   - Upgrade to a newer Java version

3. **Performance issues**
   - Try using a newer Java version for better performance
   - Java 21 offers the best performance for modern servers

### AI Error Fixer Integration

The AI error fixer automatically:
- Detects Java version mismatches
- Suggests appropriate Java versions
- Can automatically switch Java versions if needed
- Monitors for Java-related errors

## Configuration

The Java version selection can be configured in the AI error fixer config:

```json
{
  "ai_error_fixer": {
    "java_version_mapping": {
      "legacy": "8",
      "modern": "17", 
      "latest": "21"
    }
  }
}
```

## Performance Comparison

| Java Version | Memory Usage | Startup Time | Runtime Performance |
|--------------|--------------|--------------|-------------------|
| Java 8 | Low | Fast | Good |
| Java 11 | Medium | Medium | Better |
| Java 17 | Medium | Medium | Best |
| Java 21 | Medium | Fast | Excellent |

## Recommendations

1. **For production servers**: Use the latest Java version compatible with your modpack
2. **For legacy modpacks**: Stick with Java 8 for maximum compatibility
3. **For performance**: Use Java 21 for modern servers
4. **For stability**: Use Java 17 as a good middle ground

## Migration Guide

When upgrading Java versions:

1. **Backup your server data**
2. **Test with the new Java version**
3. **Monitor for any compatibility issues**
4. **Update mods if necessary**
5. **Adjust JVM arguments if needed**

The AI error fixer will help automate this process and detect any issues during migration.
