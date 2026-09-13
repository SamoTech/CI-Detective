#!/usr/bin/env python3
"""Intentional CI failure used only by the integration workflow."""

print("Running CI Detective integration fixture v3")
raise TypeError("classify() missing 1 required positional argument: 'config'")
