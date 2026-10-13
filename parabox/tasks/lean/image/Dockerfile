FROM docker.io/library/ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git zstd libgmp-dev \
    && rm -rf /var/lib/apt/lists/*
ENV ELAN_HOME=/usr/local/elan
ENV PATH=/usr/local/elan/bin:${PATH}
RUN curl -sSfL https://elan.lean-lang.org/elan-init.sh | sh -s -- -y --default-toolchain leanprover/lean4:v4.33.1
WORKDIR /opt/parabox
COPY lean-toolchain lakefile.toml ./
RUN mkdir -p Problems Audit /workspace && chmod 1777 /workspace
ENV LEAN_NUM_THREADS=4
RUN lake update && lake exe cache get
COPY Problems Problems
RUN lake build
COPY Audit Audit
RUN lake env lean Audit/Scan.lean
