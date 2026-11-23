# SPDX-License-Identifier: Apache-2.0
# -*- coding: utf-8 -*-
"""`python -m aitb` 入口，与 `aitb` console script 等价。"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
