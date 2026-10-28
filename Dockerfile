# syntax=docker/dockerfile:1
# Debian 13 (trixie): LilyPond 2.24.4. Bookworm's 2.24.1 cannot make PDFs with
# current Ghostscript security updates (the `finddevice` operator was removed).
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    SCORES_DIR=/scores
RUN apt-get update \
 && apt-get install -y --no-install-recommends lilypond python3 fonts-texgyre fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && fc-cache -f
# warm-up: the first LilyPond run builds caches; do it at image build, not on the first tap.
# Not silent (-s), so a broken LilyPond/Ghostscript shows its error in the build log.
RUN lilypond --version | head -n 1 \
 && mkdir /warm && cd /warm \
 && printf '\\version "2.24.0"\n{ c4 }\n' > w.ly && lilypond w.ly && test -s w.pdf \
 && cd / && rm -rf /warm
WORKDIR /app
COPY server.py /app/
COPY static /app/static
# PDF viewer bundled into the image (phone needs no CDN to view scores)
ADD --chmod=644 https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js /app/static/pdf.min.js
ADD --chmod=644 https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js /app/static/pdf.worker.min.js
EXPOSE 8090
CMD ["python3", "/app/server.py"]
