.PHONY: test run

PYTHON ?= python

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

run:
	./salvage ./input_dir ./output_dir
