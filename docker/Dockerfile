# A3 Constructa — development image.
#
# Thin layer over the official Frappe bench image. It does three things the
# stock image cannot do for us:
#
#   1. creates /workspace owned by `frappe`, so the named volume Docker mounts
#      there inherits that ownership instead of coming up root-owned (a
#      root-owned bench directory makes `bench init` fail);
#   2. pins Node to a line the Frappe v15 build is happy with, rather than
#      whatever `nvm alias default` points at in the base image — which is now
#      Node 24, and v15's asset build fails on it;
#   3. adds the handful of client tools the bootstrap and the health checks use.
#
# Nothing about this app is baked in — the repository is bind-mounted live at
# /workspace/a3_constructa, so editing a file on Windows edits the app in the
# bench.

ARG BENCH_IMAGE=frappe/bench:latest
FROM ${BENCH_IMAGE}

USER root

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		curl \
		netcat-openbsd \
		mariadb-client \
		redis-tools \
	&& rm -rf /var/lib/apt/lists/*

# The bench lives in /workspace/frappe-bench. Creating these directories here,
# owned by frappe, is what makes the named volumes Docker mounts over them
# writable by frappe: a volume mounted onto a path that exists in the image
# inherits that path's ownership, and onto a path that does not exist comes up
# owned by root. `sites` and `logs` get their own volumes, so they are listed.
RUN mkdir -p /workspace/frappe-bench/sites /workspace/frappe-bench/logs \
	&& chown -R frappe:frappe /workspace

USER frappe

# Prefer Node 22 (Frappe v15's build is tested against 18–22); fall back to 20,
# then to whatever the image ships.
RUN NODE_DIR="$(ls -d /home/frappe/.nvm/versions/node/v22.* 2>/dev/null | sort -V | tail -1)"; \
	if [ -z "$NODE_DIR" ]; then \
		NODE_DIR="$(ls -d /home/frappe/.nvm/versions/node/v20.* 2>/dev/null | sort -V | tail -1)"; \
	fi; \
	if [ -z "$NODE_DIR" ]; then \
		NODE_DIR="$(ls -d /home/frappe/.nvm/versions/node/v* | sort -V | tail -1)"; \
	fi; \
	ln -sfn "$NODE_DIR" /home/frappe/node

# yarn is what bench drives the asset build with, and it is installed per Node
# version — the line selected above may not have it.
RUN /home/frappe/node/bin/npm install -g yarn

# Frappe v15 declares >=3.10,<3.15; 3.12 is the newest line with settled wheels
# for the whole dependency tree, so the bench virtualenv is built from it. The
# stock image's default `python3` is 3.14, which v15 will not install against.
#
# The repository arrives over a Windows bind mount, so its files are owned by a
# uid git does not recognise as ours; without this, every `git` call bench makes
# against apps/a3_constructa dies with "detected dubious ownership".
RUN git config --global --add safe.directory '*'

ENV PYENV_VERSION=3.12.14
ENV PATH=/home/frappe/node/bin:/home/frappe/.local/bin:/home/frappe/.pyenv/shims:/home/frappe/.pyenv/bin:/usr/local/bin:/usr/bin:/bin

WORKDIR /workspace
