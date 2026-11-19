"""Extend AI HTTP client package.

This is the only code that talks to the Extend API.
Nothing outside this package may contain the literal base URL.
"""

# Single canonical source for the Extend base URL.
# config.py imports this constant so the string never appears outside this package.
EXTEND_BASE_URL = "https://api.extend.ai"
