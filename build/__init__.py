"""Packaging scripts (M7). Not shipped: `pyproject.toml` packages `proingest` alone.

This file is here so the folder is a real package rather than a namespace one. Without
it `build/bundle.py` is reachable as both `bundle` and `build.bundle` depending on who
imports it, `mypy` refuses to check a file it can reach under two names, and the scripts
and the tests would disagree about which module they are talking about.
"""
