#!/usr/bin/env python3
"""
CityPulse Setup Script
----------------------
This script helps set up the CityPulse application by:
1. Creating a .env file template if it doesn't exist
2. Checking for required Python version
3. Validating environment variables
"""

import os
import sys
import platform

MIN_PYTHON_VERSION = (3, 10)
REQUIRED_ENV_VARS = ['MAPS_API_KEY', 'OPENAI_API_KEY', 'SECRET_KEY']
ENV_TEMPLATE = """# Google Maps API Key
MAPS_API_KEY=your_google_maps_api_key_here

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Flask Secret Key (used for session management)
SECRET_KEY=generate_a_random_secret_key

# Google Search API Credentials (optional - for future features)
GOOGLE_SEARCH_API_KEY=your_google_search_api_key_here
GOOGLE_CSE_ID=your_google_cse_id_here
"""

def check_python_version():
    """Check if the current Python version meets the minimum requirements."""
    current_version = sys.version_info[:2]
    if current_version < MIN_PYTHON_VERSION:
        print(f"Error: Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} or higher is required.")
        print(f"Current Python version: {current_version[0]}.{current_version[1]}")
        return False
    print(f"Python version check passed: {current_version[0]}.{current_version[1]}")
    return True

def setup_env_file():
    """Create a .env file template if it doesn't exist."""
    if os.path.exists('.env'):
        print(".env file already exists. Skipping template creation.")
        return
    
    with open('.env', 'w') as f:
        f.write(ENV_TEMPLATE)
    
    print(".env template created. Please edit it with your API keys.")

def validate_env_file():
    """Validate that required environment variables are set in .env file."""
    if not os.path.exists('.env'):
        print("Warning: .env file not found.")
        return False
    
    missing_vars = []
    with open('.env', 'r') as f:
        env_content = f.read()
        
    for var in REQUIRED_ENV_VARS:
        # Check if the variable exists and is not set to the template value
        if f"{var}=your" in env_content or f"{var}=generate" in env_content:
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Warning: The following environment variables need to be set in .env: {', '.join(missing_vars)}")
        return False
    
    print("Environment variable check passed.")
    return True

def main():
    """Run the setup checks and actions."""
    print("\n=== CityPulse Setup ===\n")
    
    python_check = check_python_version()
    setup_env_file()
    env_check = validate_env_file()
    
    print("\n=== Setup Summary ===")
    if python_check and env_check:
        print("All checks passed! You're ready to run the application with:")
        print("  python app.py")
    else:
        print("Please address the warnings above before running the application.")
    
    print("\nFor more information, see README.md")

if __name__ == "__main__":
    main() 