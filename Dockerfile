FROM node:24-trixie-slim@sha256:173f125896c3b47ddf056734c7ea789d04595a6a08769a8f78e0df642781fb66 AS igir
COPY src/romledger/igir.py /tmp/igir.py
RUN version=$(sed -n 's/^IGIR_VERSION = "\(.*\)"$/\1/p' /tmp/igir.py) \
    && npm install --global --prefix /opt/igir "igir@${version}"

FROM python:3.14-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv
COPY --from=igir /usr/local/bin/node /usr/local/bin/node
COPY --from=igir /opt/igir /opt/igir

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --uid 1000 --create-home --home-dir /data romledger \
    && mkdir /config \
    && chown romledger /data

ENV PATH="/app/.venv/bin:/opt/igir/bin:${PATH}" \
    ROMLEDGER_CONFIG=/config/config.toml \
    ROMLEDGER_DATA=/data/romledger
USER romledger
EXPOSE 8730
ENTRYPOINT ["romledger"]
CMD ["serve", "--host", "0.0.0.0"]
