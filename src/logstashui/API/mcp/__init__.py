"""MCP (Model Context Protocol) server exposing the REST API as tools.

Every tool is a thin wrapper over an existing ``API/*_views.py`` endpoint, so
permissions, validation, and serialization live in exactly one place.
"""
