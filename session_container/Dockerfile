FROM docker.io/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_PRIORITY=high

# X11 desktop stack + system tools
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install \
    xvfb \
    xterm \
    xdotool \
    scrot \
    imagemagick \
    sudo \
    mutter \
    x11vnc \
    net-tools \
    netcat \
    lsof \
    curl \
    git \
    unzip \
    python3 \
    python3-pip \
    software-properties-common && \
    add-apt-repository ppa:mozillateam/ppa && \
    apt-get install -y --no-install-recommends \
    firefox-esr \
    x11-apps \
    xpdf \
    gedit \
    xpaint \
    tint2 \
    galculator \
    pcmanfm \
    libreoffice && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Python packages for the tool server (installed globally — no X11 needed)
COPY session_container/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# Shared output directory for screenshots
RUN mkdir -p /tmp/outputs /tmp/.X11-unix && \
    chmod 1777 /tmp/outputs /tmp/.X11-unix

# Build-time user — holds desktop configs
ENV USERNAME=computeruse
ENV HOME=/home/$USERNAME
RUN useradd -m -s /bin/bash -d $HOME $USERNAME && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Tool server and tools — self-contained inside session_container/
COPY session_container/tools/ /opt/cua-session/tools/
COPY session_container/tool_server.py /opt/cua-session/tool_server.py
RUN chmod -R 700 /opt/cua-session/

# Desktop startup scripts and tint2 config
COPY --chown=computeruse:computeruse image/ /home/computeruse/

ARG HEIGHT=768
ARG WIDTH=1024
ENV HEIGHT=$HEIGHT
ENV WIDTH=$WIDTH
ENV DISPLAY=:1
ENV DISPLAY_NUM=1

EXPOSE 5900 8001

COPY session_container/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
