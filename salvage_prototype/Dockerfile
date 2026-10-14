FROM python:3.10-slim
WORKDIR /app
COPY src/ ./src/
COPY salvage ./salvage
RUN chmod +x /app/salvage
ENTRYPOINT ["/app/salvage"]
