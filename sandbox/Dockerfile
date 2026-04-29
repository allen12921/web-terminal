FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm-256color
ENV LANG=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash bash-completion \
    coreutils util-linux procps \
    vim nano less tree file findutils \
    grep gawk sed \
    curl wget netcat-openbsd dnsutils iputils-ping net-tools \
    git python3 python3-pip \
    tar gzip zip unzip bzip2 \
    man-db sudo passwd \
    locales \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root sandbox user
RUN useradd -m -s /bin/bash -u 1001 sandbox && \
    echo 'sandbox:sandbox' | chpasswd && \
    echo 'sandbox ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/sandbox && \
    chmod 440 /etc/sudoers.d/sandbox

# Shell prompt, welcome, and completions
RUN printf '%s\n' \
    'source /etc/bash_completion 2>/dev/null' \
    'export PS1="\[\033[01;32m\]\u@web-terminal\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ "' \
    'echo ""' \
    'echo "  Welcome to Web Terminal  "' \
    'echo "  Type commands below. Type '\''exit'\'' to close the session."' \
    'echo ""' \
    >> /home/sandbox/.bashrc && \
    chown sandbox:sandbox /home/sandbox/.bashrc

WORKDIR /home/sandbox
USER sandbox

CMD ["sleep", "infinity"]
