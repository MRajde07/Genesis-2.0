.PHONY: build test run clean

PYTHON ?= python3
PYTHON_VERSION ?= 3.12
IMAGE_NAME ?= salvage:local

# Offline by design: requires the selected python:<version>-slim base image
# to already exist in the local Docker image cache.
build:
	docker build --network=none --pull=false --build-arg PYTHON_VERSION=$(PYTHON_VERSION) -t $(IMAGE_NAME) .

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

run:
	./salvage ./input_dir ./output_dir

clean:
	rm -rf output output_dir __pycache__ .pytest_cache
