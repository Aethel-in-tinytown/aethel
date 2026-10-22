FROM node:24-bookworm-slim AS frontend
WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run typecheck && npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY aethel_pkg/ aethel_pkg/
COPY town_pkg/ town_pkg/
COPY aethel_web/ aethel_web/
COPY aethel_live.py ./
RUN pip install --no-cache-dir '.[web,fast]' && useradd --uid 10001 --create-home aethel && mkdir /data && chown aethel /data
COPY --from=frontend /build/web/dist/ web/dist/
ENV AETHEL_HOME=/data PYTHONHASHSEED=0 PYTHONUNBUFFERED=1
USER aethel
EXPOSE 8080 8081
VOLUME ["/data"]
HEALTHCHECK --interval=30s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=3)"
ENTRYPOINT ["python", "aethel_live.py", "--serve", "--host", "0.0.0.0"]
