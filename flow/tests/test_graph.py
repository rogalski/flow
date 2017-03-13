import ast
import sys
import textwrap

from flow import FlowGraph


def ast_from_text(code, filename="<unknown>"):
    return ast.parse(textwrap.dedent(code), filename)


def test_func_name():
    return sys._getframe(1).f_code.co_name


def test_from_empty_module():
    ast_root = ast_from_text("")
    graph = FlowGraph.from_ast(ast_root)
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_from_single_statement_module():
    ast_root = ast_from_text("A = 1")
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 1
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_from_two_statement_module():
    ast_root = ast_from_text("A = 1; B = 2")
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 2
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_if_conditional():
    ast_root = ast_from_text("""
    if 1:
        print(1)
    """)
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 2  # 1x in if, 1x in if body
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_if_else_conditional():
    ast_root = ast_from_text("""
    if 1:
        print(1)
    else:
        print(2)
    """)
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 3  # 1x if stmt, 2x in if bodies
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_if_elif_conditional():
    ast_root = ast_from_text("""
    if 1:
        print(1)
    elif 2:
        print(2)
    """)
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 4  # 2x if stmt, 2x in if bodies
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_if_elif_else_conditional():
    ast_root = ast_from_text("""
    if 1:
        print(1)
    elif 2:
        print(2)
    else:
        print(3)
    """)
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 5  # 2x if stmt, 3x in if bodies
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))


def test_self_graph():
    import flow.graph
    with open(flow.graph.__file__) as fd:
        module = fd.read()
    ast_root = ast_from_text(module, flow.graph.__name__)
    graph = FlowGraph.from_ast(ast_root)
    graph.to_graphviz().render('{}.gv'.format(test_func_name()))
