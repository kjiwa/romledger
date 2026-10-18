FROM node:26-trixie-slim@sha256:0d1e33586362bb9e608c4e751e7a9e7edb55c9ac11461ed5666af696cc461dd4 AS igir
COPY src/romledger/igir.py /tmp/igir.py
RUN version=$(sed -n 's/^IGIR_VERSION = "\(.*\)"$/\1/p' /tmp/igir.py) \
    && test -n "$version" \
    && npm install --global --prefix /opt/igir "igir@${version}"

FROM python:3.14-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=igir /usr/local/bin/node /usr/local/bin/node
COPY --from=igir /opt/igir /opt/igir

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --uid 1000 --create-home romledger \
    && mkdir /config /data \
    && chown romledger /data

ENV PATH="/app/.venv/bin:/opt/igir/bin:${PATH}" \
    ROMLEDGER_CONFIG=/config/config.toml \
    ROMLEDGER_DATA=/data/romledger
USER romledger
LABEL org.opencontainers.image.source="https://github.com/kjiwa/romledger"
EXPOSE 8730
ENTRYPOINT ["romledger"]
CMD ["serve", "--host", "0.0.0.0"]
