from __future__ import annotations

from pathlib import Path

from .ast_node import (
    AndNode,
    AArgChar,
    ArithForNode,
    ArgChar,
    AssignNode,
    BArgChar,
    CaseNode,
    CommandNode,
    DefunNode,
    DupRedirNode,
    FileRedirNode,
    HeredocRedirNode,
    ForNode,
    IfNode,
    NotNode,
    OrNode,
    PipeNode,
    PArgChar,
    RedirNode,
    CArgChar,
    QArgChar,
    SingleArgRedirNode,
    SubshellNode,
    WhileNode,
    make_typed_semi_sequence,
    string_of_arg,
)


def _missing_dependency_error() -> ImportError:
    return ImportError(
        "bash Tree-sitter support requires the optional 'treesitter' dependencies; "
        "install with `pip install shasta[treesitter]`"
    )


def language():
    try:
        import tree_sitter_bash
        from tree_sitter import Language
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    return Language(tree_sitter_bash.language())


def parser():
    try:
        from tree_sitter import Parser
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    bash_parser = Parser(language())
    return bash_parser


def parse_bytes(source: bytes):
    return parser().parse(source)


def parse(source: str):
    return parse_bytes(source.encode("utf-8", errors="surrogateescape"))


def parse_file(path: str | Path):
    return parse_bytes(Path(path).read_bytes())


def to_ast_nodes(source: str):
    source_bytes = source.encode("utf-8", errors="surrogateescape")
    return _program_to_ast_nodes(parse_bytes(source_bytes).root_node, source_bytes)


def to_ast_node(source: str):
    nodes = to_ast_nodes(source)
    if not nodes:
        raise ValueError("no commands found")
    return make_typed_semi_sequence(nodes)


def _program_to_ast_nodes(node, source: bytes):
    if node.type != "program":
        raise NotImplementedError(f"expected program, got {node.type}")
    if node.has_error:
        raise SyntaxError("Tree-sitter reported a parse error")
    return [_convert(child, source) for child in _named_children(node)]


def _named_children(node):
    return [child for child in node.named_children if child.type != "comment"]


_COMMAND_NODES = {
    "command",
    "redirected_statement",
    "pipeline",
    "list",
    "if_statement",
    "for_statement",
    "c_style_for_statement",
    "while_statement",
    "case_statement",
    "subshell",
    "function_definition",
    "declaration_command",
    "unset_command",
    "test_command",
    "negated_command",
    "compound_statement",
    "do_group",
    "variable_assignment",
    "variable_assignments",
    "file_redirect",
}


def _convert(node, source: bytes):
    if node.type == "command":
        return _command(node, source)
    if node.type in {"declaration_command", "unset_command", "test_command"}:
        return _literal_command(node, source)
    if node.type == "variable_assignment":
        return CommandNode(None, [_assignment(node, source)], [], [])
    if node.type == "variable_assignments":
        return CommandNode(None, [_assignment(child, source) for child in node.named_children], [], [])
    if node.type == "file_redirect":
        return RedirNode(None, CommandNode(None, [], [], []), [_file_redirect(node, source)])
    if node.type == "redirected_statement":
        return _redirected_statement(node, source)
    if node.type == "pipeline":
        return PipeNode(False, [_convert(child, source) for child in _named_children(node)])
    if node.type == "subshell":
        return SubshellNode(None, make_typed_semi_sequence([_convert(child, source) for child in _named_children(node)]), [])
    if node.type == "list":
        return _list(node, source)
    if node.type == "for_statement":
        return _for_statement(node, source)
    if node.type == "c_style_for_statement":
        return _c_style_for_statement(node, source)
    if node.type == "while_statement":
        return _while_statement(node, source)
    if node.type == "if_statement":
        return _if_statement(node, source)
    if node.type == "case_statement":
        return _case_statement(node, source)
    if node.type == "function_definition":
        return _function_definition(node, source)
    if node.type == "negated_command":
        return NotNode(_convert(node.named_children[0], source), no_braces=True)
    if node.type in {"compound_statement", "do_group"}:
        if node.type == "compound_statement" and any(child.type in {"binary_expression", "unary_expression", "postfix_expression", "ternary_expression"} for child in node.named_children):
            return _literal_command(node, source)
        return make_typed_semi_sequence([_convert(child, source) for child in _named_children(node)])
    if node.type in {"command_name", "variable_name", "subscript", "binary_expression", "unary_expression", "postfix_expression", "ternary_expression"}:
        return _literal_command(node, source)
    raise NotImplementedError(f"unsupported Tree-sitter bash node: {node.type}")


def _command(node, source: bytes):
    assignments = []
    arguments = []
    redir_list = []
    for child in node.named_children:
        if child.type == "variable_assignment":
            assignments.append(_assignment(child, source))
        elif child.type in {"file_redirect", "herestring_redirect"}:
            redir = _redir(child, source)
            fd_token = node.named_children[node.named_children.index(child) - 1]
            if (
                fd_token.type == "number"
                and fd_token.end_byte == child.start_byte
                and hasattr(redir, "fd")
                and arguments
            ):
                arguments.pop()
                redir.fd = ("fixed", int(_text(fd_token, source)))
            redir_list.append(redir)
        elif child.type == "command_name":
            arguments.append(_arg(child.named_children[0], source) if child.named_children else _arg(child, source))
        else:
            arguments.append(_arg(child, source))
    return CommandNode(None, assignments, arguments, redir_list)


def _literal_command(node, source: bytes):
    return CommandNode(None, [], [_chars(_text(node, source))], [])


def _redirected_statement(node, source: bytes):
    command_node = node.named_children[0]
    command = _convert(command_node, source)
    redirs = []
    for child in node.named_children[1:]:
        redir = _redir(child, source)
        fd_token = command_node.named_children[-1] if command_node.named_children else None
        if (
            fd_token is not None
            and fd_token.type == "number"
            and fd_token.end_byte == child.start_byte
            and hasattr(redir, "fd")
            and command.arguments
        ):
            command.arguments.pop()
            redir.fd = ("fixed", int(_text(fd_token, source)))
        redirs.append(redir)
    return RedirNode(None, command, redirs)


def _list(node, source: bytes):
    operands = [_convert(child, source) for child in node.named_children]
    if not operands:
        return CommandNode(-1, [], [], [])
    operators = [_text(child, source) for child in node.children if child.type in {"&&", "||"}]
    acc = operands[0]
    for operator, operand in zip(operators, operands[1:]):
        if operator == "&&":
            acc = AndNode(acc, operand, no_braces=True)
        elif operator == "||":
            acc = OrNode(acc, operand, no_braces=True)
    return acc


def _for_statement(node, source: bytes):
    named = node.named_children
    variable = _arg(named[0], source)
    body = _convert(named[-1], source)
    words = named[1:-1]
    if words and words[0].type == "do_group":
        words = []
    return ForNode(None, [_arg(word, source) for word in words], body, variable)


def _c_style_for_statement(node, source: bytes):
    named = node.named_children
    body = _convert(named[-1], source)
    exprs = named[:-1]
    parts = [[_text(expr, source)] for expr in exprs]
    while len(parts) < 3:
        parts.append([])
    return ArithForNode(None, [_chars(x) for x in parts[0]], [_chars(x) for x in parts[1]], [_chars(x) for x in parts[2]], body)


def _while_statement(node, source: bytes):
    named = node.named_children
    return WhileNode(_convert(named[0], source), _convert(named[-1], source))


def _if_statement(node, source: bytes):
    named = node.named_children
    cond = _convert(named[0], source)
    then_b = _convert(named[1], source)
    else_b = _convert(named[2].named_children[0], source) if len(named) > 2 else None
    return IfNode(cond, then_b, else_b)


def _case_statement(node, source: bytes):
    named = node.named_children
    return CaseNode(None, _arg(named[0], source), [_case_item(child, source) for child in named[1:]])


def _case_item(node, source: bytes):
    patterns = []
    body = []
    for child in node.named_children:
        if child.type in _COMMAND_NODES:
            body.append(_convert(child, source))
        else:
            patterns.append(_arg(child, source))
    if not body:
        body = [CommandNode(-1, [], [], [])]
    return {"cpattern": patterns, "cbody": make_typed_semi_sequence(body), "fallthrough": False}


def _function_definition(node, source: bytes):
    name = _arg(node.named_children[0], source)
    body = _convert(node.named_children[-1], source)
    return DefunNode(None, name, body, bash_mode=True)


def _assignment(node, source: bytes):
    var = _text(node.named_children[0], source)
    value = node.named_children[1] if len(node.named_children) > 1 else None
    return AssignNode(var, _arg(value, source) if value else [])


def _redir(node, source: bytes):
    if node.type == "herestring_redirect":
        word = node.named_children[-1]
        return FileRedirNode("ReadingString", ("fixed", 0), _arg(word, source))
    if node.type == "heredoc_redirect":
        start = node.child_by_field_name("heredoc_start") or node.named_children[0]
        body_nodes = [child for child in node.named_children if child.type in {"heredoc_body", "heredoc_content"}]
        body = _chars(_text(body_nodes[0], source).rstrip("\n")) if body_nodes else []
        return HeredocRedirNode("Here", ("fixed", 0), _arg(start, source), body)
    return _file_redirect(node, source)


def _file_redirect(node, source: bytes):
    op = next(child.type for child in node.children if not child.is_named)
    fd_node = next((child for child in node.named_children if child.type == "file_descriptor"), None)
    fd = ("fixed", int(_text(fd_node, source))) if fd_node else None
    if op in {">&-", "<&-"}:
        return SingleArgRedirNode("CloseThis", fd or ("fixed", 1))
    word_nodes = [child for child in node.named_children if child.type != "file_descriptor"]
    if not word_nodes:
        raise ValueError(f"redirect without target: {_text(node, source)}")
    word = word_nodes[-1]
    redir_type = {">": "To", ">>": "Append", "<": "From", ">|": "Clobber", "<>": "FromTo"}.get(op)
    if op == "&>":
        return SingleArgRedirNode("ErrAndOut", ("var", _arg(word, source)))
    if op == "&>>":
        return SingleArgRedirNode("AppendErrAndOut", ("var", _arg(word, source)))
    if op in {">&", "<&"}:
        target_text = _text(word, source)
        target = ("fixed", int(target_text)) if target_text.isdigit() else ("var", _arg(word, source))
        return DupRedirNode("ToFD" if op == ">&" else "FromFD", fd or ("fixed", 1 if op == ">&" else 0), target)
    if redir_type is None:
        raise NotImplementedError(f"unsupported redirect operator: {op}")
    if fd is None:
        fd = ("fixed", 0 if redir_type == "From" else 1)
    return FileRedirNode(redir_type, fd, _arg(word, source))


def _arg(node, source: bytes) -> list[ArgChar]:
    if node.type in {"command_name", "binary_expression", "unary_expression", "postfix_expression", "ternary_expression", "parenthesized_expression", "variable_name", "special_variable_name", "test_operator", "subscript", "regex", "array", "extglob_pattern", "brace_expression"}:
        return _chars(_text(node, source))
    if node.type == "string":
        return [QArgChar(_arg_parts(node, source))]
    if node.type == "concatenation":
        return _arg_parts(node, source)
    if node.type == "command_substitution":
        return [BArgChar(make_typed_semi_sequence([_convert(child, source) for child in _named_children(node)]))]
    if node.type == "process_substitution":
        op = next(child.type for child in node.children if not child.is_named and child.type in {"<(", ">("})
        return [PArgChar(op, make_typed_semi_sequence([_convert(child, source) for child in _named_children(node)]))]
    if node.type == "arithmetic_expansion":
        return [AArgChar(_chars(_text(node.named_children[0], source)))]
    return _chars(_text(node, source))


def _arg_parts(node, source: bytes) -> list[ArgChar]:
    parts = []
    for child in node.children:
        if not child.is_named:
            continue
        if child.type in {"command_substitution", "process_substitution", "arithmetic_expansion"}:
            parts.extend(_arg(child, source))
        else:
            parts.extend(_chars(_text(child, source)))
    return parts


def _chars(text: str) -> list[ArgChar]:
    return [CArgChar(ord(char), bash_mode=True) for char in text]


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="surrogateescape")
