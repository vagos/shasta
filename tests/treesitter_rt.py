#!/usr/bin/env python3

from __future__ import annotations

import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from shasta.treesitter_to_shasta_ast import to_ast_node  # noqa: E402


BASH_TESTS_DIR = os.path.join(os.path.dirname(__file__), "bash_tests", "test_files")


def _test_files() -> list[str]:
    return sorted(
        os.path.join(BASH_TESTS_DIR, name)
        for name in os.listdir(BASH_TESTS_DIR)
        if name.endswith((".sub", ".tests"))
    )


def _roundabout(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as handle:
        source = handle.read()
    first = to_ast_node(source).pretty()
    second = to_ast_node(first).pretty()
    if second != first:
        raise AssertionError("second pretty output differed from first")
    return first


def main() -> int:
    passed = failed = 0
    for path in _test_files():
        relpath = os.path.relpath(path, os.path.dirname(__file__))
        try:
            _roundabout(path)
        except Exception as exc:
            failed += 1
            print(f"FAIL {relpath}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {relpath}")

    print(f"treesitter corpus: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
