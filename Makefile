.PHONY: setup install run clean

# Default target executed when no arguments are given to make.
all: help

# Define a variable for the Python interpreter
PYTHON := python3.10

# Check if virtual environment exists, if not create it
venv:
	@if [ ! -d ".venv_py310" ]; then \
		echo "Creating virtual environment..."; \
		$(PYTHON) -m venv .venv_py310; \
	fi

# Setup the project
setup: venv
	@echo "Setting up CityPulse..."
	@. .venv_py310/bin/activate && $(PYTHON) setup.py

# Install dependencies
install: venv
	@echo "Installing dependencies..."
	@. .venv_py310/bin/activate && pip install -r requirements.txt

# Run the application
run: venv
	@echo "Starting CityPulse..."
	@. .venv_py310/bin/activate && $(PYTHON) app.py

# Clean up Python cache files
clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.pyd" -delete
	@find . -type f -name ".DS_Store" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type d -name "*.egg" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@echo "Cleanup complete!"

# Show help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  setup    - Setup the project and create .env template"
	@echo "  install  - Install dependencies"
	@echo "  run      - Run the application"
	@echo "  clean    - Remove Python cache files"
	@echo "  help     - Show this help message"
	@echo ""
	@echo "Example:"
	@echo "  make setup install run" 