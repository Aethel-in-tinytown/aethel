#!/usr/bin/env python3
"""Aethel — thin entry point.

The organism lives in aethel_pkg/ (v0.16: clean architecture, same soul).
This file stays at the historic path so watchdogs, crons, and Donald's
references keep working unchanged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aethel_pkg.main import main

if __name__ == "__main__":
    main()
