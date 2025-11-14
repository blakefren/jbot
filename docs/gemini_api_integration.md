# Gemini API Integration Design Document

## Objective

This document outlines the design and implementation of the integration of the Gemini API into the `jbot` application. The goal is to create a flexible and extensible system for interacting with external APIs, with Gemini being the first one.

## Core Components

### 1. Generic API Manager

A new `APIManager` class was created in `src/core/api_manager.py`. This class provides a generic framework for making authenticated GET and POST requests to any RESTful API.

**Key Features:**
- Handles API key authentication through headers.
- Provides `get()` and `post()` methods for common HTTP requests.
- Includes basic error handling for network-related issues.

### 2. Gemini API Manager

A `GeminiManager` class, which inherits from `APIManager`, was created in `src/core/gemini_manager.py`. This class is specifically designed to interact with the Google Gemini API.

**Key Features:**
- Sets the base URL for the Gemini API.
- Implements a `generate_content()` method to send text prompts to the `gemini-pro` model.

### 3. Configuration

To securely manage the Gemini API key, the following changes were made:
- A new entry `GEMINI_API_KEY` was added to the `.env.template` file.
- The `ConfigReader` class in `src/cfg/main.py` was updated with a `get_gemini_api_key()` method to retrieve the key from the environment variables.

### 4. Integration into the Application

The `GeminiManager` is initialized and registered with the `GameRunner` in `src/core/discord.py`. This makes it available to other parts of the application, such as cogs, that might use its functionality. The initialization is wrapped in a `try...except` block to handle cases where the API key is not configured, allowing the bot to run without Gemini functionality if the key is missing.

## File Changes

### Created Files
- `src/core/api_manager.py`: The generic API manager.
- `src/core/gemini_manager.py`: The specific manager for the Gemini API.
- `docs/gemini_api_integration.md`: This design document.

### Modified Files
- `src/cfg/main.py`: Added a method to read the `GEMINI_API_KEY` from environment variables.
- `.env.template`: Added `GEMINI_API_KEY` for users to configure.
- `src/core/discord.py`: Integrated and initialized the `GeminiManager`.
