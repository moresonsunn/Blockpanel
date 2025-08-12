FROM openjdk:21-jdk-slim

# Install tools and available Java versions
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install Java 8 (Eclipse Temurin)
RUN wget -qO- https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u392-b08/OpenJDK8U-jdk_x64_linux_hotspot_8u392b08.tar.gz | tar -xz -C /opt/ && \
    ln -sf /opt/jdk8u392-b08/bin/java /usr/local/bin/java8

# Download and install Java 11 (Eclipse Temurin)
RUN wget -qO- https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.21%2B9/OpenJDK11U-jdk_x64_linux_hotspot_11.0.21_9.tar.gz | tar -xz -C /opt/ && \
    ln -sf /opt/jdk-11.0.21+9/bin/java /usr/local/bin/java11

# Download and install Java 17 (Eclipse Temurin)
RUN wget -qO- https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.9%2B9/OpenJDK17U-jdk_x64_linux_hotspot_17.0.9_9.tar.gz | tar -xz -C /opt/ && \
    ln -sf /opt/jdk-17.0.9+9/bin/java /usr/local/bin/java17

# Create symlink for Java 21 (already installed in base image)
RUN ln -sf /usr/local/openjdk-21/bin/java /usr/local/bin/java21

# Set default Java version
ENV JAVA_BIN=/usr/local/bin/java21

WORKDIR /data
EXPOSE 25565
COPY runtime-entrypoint.sh /usr/local/bin/runtime-entrypoint.sh
RUN chmod +x /usr/local/bin/runtime-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/runtime-entrypoint.sh"]
