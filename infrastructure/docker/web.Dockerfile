# Inland Resilience web app (React + Vite + MapLibre), dev server with the /v1 proxy to the API.
FROM node:24-bookworm-slim
WORKDIR /app
RUN chown node /app
USER node
COPY --chown=node apps/web/package.json apps/web/package-lock.json ./
RUN --mount=type=cache,target=/home/node/.npm,uid=1000 npm ci --no-audit --no-fund
COPY --chown=node apps/web ./
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
