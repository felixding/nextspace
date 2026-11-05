FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
RUN apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential autoconf automake libtool pkg-config curl ca-certificates \
    meson ninja-build python3 python3-pil gdb gnustep-make libgnustep-gui-dev libgnustep-base-dev hwdata \
    libwlroots-0.18-dev=0.18.2-3 wayland-protocols=1.44-1 \
    libwayland-dev libxkbcommon-dev libsystemd-dev liblcms2-dev libcairo2-dev libpango1.0-dev libfontconfig-dev fontconfig \
    libfreetype-dev libffi-dev libgl-dev \
    libtiff-dev libjpeg-dev libpng-dev libgif-dev libmagickcore-dev libicu-dev librsvg2-bin poppler-utils ghostscript \
    libxml2-dev libxslt1-dev libgnutls28-dev libgmp-dev libavahi-client-dev libcurl4-gnutls-dev \
    fonts-dejavu-core fonts-noto-cjk xcursor-themes dbus-daemon dbus-bin passwd swaylock=1.8.2-1 \
    fcitx5=5.1.12-2 fcitx5-pinyin=5.1.8-1 fcitx5-hangul=5.1.6-1 \
    libgtk-4-dev qt6-base-dev qt6-wayland weston=14.0.2-1 wayland-utils=1.2.0-2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
ENV NEXTSPACE_TEST_LOCK_PAM=1
COPY . .
CMD ["sh", "Tests/Wayland/build.sh"]
