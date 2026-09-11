# Clean GitHub builds obtain public data themselves. No local vault or data COPY.
FROM python:3.12-slim AS dependencies
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements-pilot.txt ./
RUN pip install --no-cache-dir -r requirements-pilot.txt

FROM dependencies AS connectome
COPY fetch_connectome.py build_graph.py ./
RUN python fetch_connectome.py && python build_graph.py

FROM node:22-slim AS contracts
WORKDIR /compiler
RUN npm install --no-audit --no-fund solc@0.8.30
COPY contracts/ ./contracts/
COPY compile-cloud-contracts.cjs ./
RUN node compile-cloud-contracts.cjs

FROM dependencies AS garden
ENV PORT=8080
COPY --from=connectome /app/build/graph.npz ./build/graph.npz
COPY --from=connectome /app/data/body-annotations.feather ./data/body-annotations.feather
COPY --from=connectome /app/data/sources.json ./data/sources.json
COPY --from=contracts /compiler/build/FlyGarden.json ./build/FlyGarden.json
COPY --from=contracts /compiler/build/QuoteProbe.json ./build/QuoteProbe.json
COPY *.py ./
COPY pilot_config.json ./
COPY contracts/ ./contracts/
COPY web/wallets.json ./web/wallets.json
COPY web/index.html web/observatory.css web/observatory.js ./web/
RUN mkdir -p /app/.garden
EXPOSE 8080
CMD ["python", "-u", "live_runner.py"]
