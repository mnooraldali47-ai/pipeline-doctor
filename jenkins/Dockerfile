FROM jenkins/jenkins:lts

USER root

# Python 3.11 + pip
# /etc/pip.conf disables PEP 668 "externally-managed" guard (Debian Bookworm)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3.11 \
      python3-pip \
 && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
 && ln -sf /usr/bin/python3.11 /usr/bin/python \
 && ln -sf /usr/bin/pip3 /usr/bin/pip \
 && printf '[global]\nbreak-system-packages = true\n' > /etc/pip.conf \
 && rm -rf /var/lib/apt/lists/*

# Docker CLI (kept for potential future use)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg lsb-release \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
      https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

USER jenkins
