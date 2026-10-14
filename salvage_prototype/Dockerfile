# Python version is supplied at build time, e.g. --build-arg PYTHON_VERSION=3.11.
# This image intentionally installs no packages and performs no network access.
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY . /app
RUN chmod 0755 /app/salvage

# Pass input and output paths as arguments, for example:
# docker run --rm --network=none -v "$PWD/input_dir:/data/in:ro" \
#   -v "$PWD/output_dir:/data/out" salvage:local /data/in /data/out
ENTRYPOINT ["./salvage"]
