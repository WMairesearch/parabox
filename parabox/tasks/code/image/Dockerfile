FROM docker.io/library/python:3.12-slim-bookworm@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a
COPY requirements.txt /tmp/parabox-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/parabox-requirements.txt
COPY pip.conf /etc/pip.conf
RUN mkdir -p /var/cache/pip /workspace && chmod 1777 /var/cache/pip /workspace
WORKDIR /workspace
