# Dockerfile for building static Git binaries on Linux (Alpine/musl)
#
# This creates fully static Git binaries with HTTPS support that can run
# on any Linux distribution (glibc or musl based).
#
# Build:
#   docker build -t git-builder-linux -f build/linux/Dockerfile .
#   docker run --rm -v $(pwd)/dist:/output git-builder-linux
#
# For ARM64:
#   docker buildx build --platform linux/arm64 -t git-builder-linux-arm64 -f build/linux/Dockerfile .

ARG ALPINE_VERSION=3.19
FROM alpine:${ALPINE_VERSION} AS builder

# Git version to build
ARG GIT_VERSION=2.47.1
ARG CURL_VERSION=8.11.1

# Install build dependencies (no pcre2 - we use git's built-in regex)
RUN apk add --no-cache \
    build-base \
    openssl-dev \
    openssl-libs-static \
    zlib-dev \
    zlib-static \
    curl \
    perl \
    xz

# Build dependencies in a separate directory to allow removing .so files safely
# This approach is borrowed from python-build-standalone
ENV DEPS_DIR=/opt/deps

# Build curl from source with minimal dependencies (no libidn2, no psl)
# This avoids symbol conflicts with git's error() function
WORKDIR /curl-build
RUN curl -fsSL "https://curl.se/download/curl-${CURL_VERSION}.tar.xz" | tar -xJ --strip-components=1

RUN ./configure \
    --prefix=${DEPS_DIR} \
    --disable-shared \
    --enable-static \
    --with-openssl \
    --with-zlib \
    --without-libidn2 \
    --without-libpsl \
    --without-brotli \
    --without-zstd \
    --without-nghttp2 \
    --without-libssh2 \
    --without-libssh \
    --without-librtmp \
    --disable-ldap \
    --disable-ldaps \
    --disable-rtsp \
    --disable-dict \
    --disable-telnet \
    --disable-tftp \
    --disable-pop3 \
    --disable-imap \
    --disable-smb \
    --disable-smtp \
    --disable-gopher \
    --disable-mqtt \
    --disable-manual

RUN make -j$(nproc) && make install

# Copy static libraries from system to deps dir, then remove ALL .so from deps
# This ensures the linker only sees static libraries in DEPS_DIR
RUN cp /usr/lib/libssl.a /usr/lib/libcrypto.a /lib/libz.a ${DEPS_DIR}/lib/ && \
    find ${DEPS_DIR} -name '*.so*' -delete

# Build Git
WORKDIR /src
RUN curl -fsSL "https://mirrors.edge.kernel.org/pub/software/scm/git/git-${GIT_VERSION}.tar.xz" \
    | tar -xJ --strip-components=1

# Build Git with static linking
# Point to our deps directory where only static libraries exist
RUN make -j$(nproc) \
    prefix=/usr \
    gitexecdir=/usr/libexec/git-core \
    NO_GETTEXT=1 \
    NO_TCLTK=1 \
    NO_PERL=1 \
    NO_PYTHON=1 \
    NO_EXPAT=1 \
    NO_INSTALL_HARDLINKS=1 \
    NO_REGEX=NeedsStartEnd \
    NO_LIBPCRE2=1 \
    CFLAGS="-I${DEPS_DIR}/include" \
    LDFLAGS="-static -L${DEPS_DIR}/lib" \
    CURL_LDFLAGS="-L${DEPS_DIR}/lib -lcurl -lssl -lcrypto -lz -lpthread" \
    all

# Install to staging directory (need to pass same flags as build)
RUN make -j$(nproc) \
    prefix=/usr \
    gitexecdir=/usr/libexec/git-core \
    NO_GETTEXT=1 \
    NO_TCLTK=1 \
    NO_PERL=1 \
    NO_PYTHON=1 \
    NO_EXPAT=1 \
    NO_INSTALL_HARDLINKS=1 \
    NO_REGEX=NeedsStartEnd \
    NO_LIBPCRE2=1 \
    CFLAGS="-I${DEPS_DIR}/include" \
    LDFLAGS="-static -L${DEPS_DIR}/lib" \
    CURL_LDFLAGS="-L${DEPS_DIR}/lib -lcurl -lssl -lcrypto -lz -lpthread" \
    DESTDIR=/git-install \
    install

# Verify static linking - FAIL if not static to prevent broken wheels
RUN echo "Verifying static linking..." && \
    file /git-install/usr/bin/git && \
    (ldd /git-install/usr/bin/git 2>&1 | grep -q "Not a valid dynamic program" || \
     ldd /git-install/usr/bin/git 2>&1 | grep -q "statically linked" || \
     (echo "ERROR: Binary is not statically linked!" && ldd /git-install/usr/bin/git && exit 1))

# Test the binary
RUN /git-install/usr/bin/git --version

# Create minimal distribution structure
FROM alpine:${ALPINE_VERSION} AS packager

COPY --from=builder /git-install /git-install

# Reorganize for distribution
WORKDIR /dist
RUN mkdir -p bin libexec && \
    cp /git-install/usr/bin/git bin/ && \
    cp -r /git-install/usr/libexec/git-core libexec/ && \
    mkdir -p share && \
    cp -r /git-install/usr/share/git-core share/ 2>/dev/null || true

# Strip binaries to reduce size
RUN apk add --no-cache binutils && \
    find /dist -type f -executable -exec strip --strip-all {} \; 2>/dev/null || true

# Show final size
RUN echo "Distribution contents:" && \
    find /dist -type f -exec ls -lh {} \; && \
    echo "Total size:" && \
    du -sh /dist

# Final stage
FROM alpine:${ALPINE_VERSION} AS runner

COPY --from=packager /dist /dist

# Test the installation
RUN /dist/bin/git --version && \
    echo "Testing HTTPS support..." && \
    GIT_EXEC_PATH=/dist/libexec/git-core /dist/bin/git ls-remote --heads https://github.com/git/git.git 2>&1 | head -1 || \
    echo "HTTPS test completed (may fail without network)"

ENTRYPOINT ["/bin/sh", "-c"]
CMD ["cp -r /dist/* /output/ && echo 'Files copied to /output'"]
