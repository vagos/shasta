from __future__ import annotations

import pytest

from shasta.ast_node import AArgChar
from shasta.treesitter_to_shasta_ast import parse, to_ast_node


pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_bash")


def test_parse_bash_script_with_tree_sitter():
    tree = parse("for x in a b; do echo \"$x\"; done\n")

    assert tree.root_node.type == "program"
    assert not tree.root_node.has_error


@pytest.mark.parametrize(
    "source",
    [
        "echo hi\n",
        "x=1 echo hi >out\n",
        "echo hi | wc -c\n",
        "echo hi && echo bye\n",
        "if true; then echo yes; else echo no; fi\n",
        "for x in a b; do echo $x; done\n",
        "foo() { echo hi; }\n",
        "echo $(date)\n",
        "echo \"today is $(date)\"\n",
        "x=$(echo hi)\n",
        "cat <(echo hi)\n",
        "diff <(sort a) <(sort b)\n",
        "cat >(grep hi)\n",
        "echo $name ${name:-world} ${#name}\n",
        "echo ${name%.*} ${name#pre} ${name//a/b}\n",
        "echo $1 $? $# $@ $* $$ $!\n",
        "echo $((1 + x))\n",
        "echo 'single $name'\n",
        "echo $'a\\n'\n",
        "echo a${b}c pre$(date)post\n",
    ],
)
def test_tree_sitter_to_shasta_roundabout(source):
    first = to_ast_node(source).pretty()
    second = to_ast_node(first).pretty()

    assert second == first


def test_arithmetic_expansion_uses_shasta_node():
    node = to_ast_node("echo $((1 + 1))")

    assert isinstance(node.arguments[1][0], AArgChar)
    assert node.pretty() == "echo $((1 + 1))"
