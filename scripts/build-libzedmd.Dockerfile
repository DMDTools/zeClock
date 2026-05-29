# Docker-based builder for libzedmd (Linux x64)
# Produces .so files that can be copied to ~/.zeclock/lib/
#
# Usage:
#   docker build -f scripts/build-libzedmd.Dockerfile -o ~/.zeclock/lib .
#
# Or via the helper script:
#   scripts/build-libzedmd.sh

FROM gcc:14 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake bash curl ca-certificates \
    libtool automake autoconf pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone libzedmd at latest release tag
RUN set -e && \
    VERSION=$(curl -s https://api.github.com/repos/PPUC/libzedmd/releases/latest | \
      grep -oP '"tag_name":\s*"\K[^"]+') && \
    echo "$VERSION" > /build/version.txt && \
    git clone --depth 1 --branch "$VERSION" \
      https://github.com/PPUC/libzedmd.git /build/libzedmd

WORKDIR /build/libzedmd

# Build external dependencies (cargs, libserialport, sockpp, libframeutil)
RUN bash platforms/linux/x64/external.sh

# Build libzedmd itself
RUN cmake -DPLATFORM=linux -DARCH=x64 -DCMAKE_BUILD_TYPE=Release -B build && \
    cmake --build build -- -j$(nproc)

# Collect all runtime .so files into /output
RUN mkdir -p /output && \
    find build -name '*.so*' -exec cp -a {} /output/ \; && \
    find third-party/runtime-libs/linux/x64 -name '*.so*' -exec cp -a {} /output/ \; 2>/dev/null || true && \
    cp /build/version.txt /output/.libzedmd-version

# --- Output stage: only the .so files ---
FROM scratch
COPY --from=builder /output/ /
