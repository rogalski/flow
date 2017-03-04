import ast
import sys
import textwrap

from flow import FlowGraph


def test_from_empty_module():
    ast_root = ast.parse("")
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 0
    graph.to_graphviz().render(sys._getframe().f_code.co_name + '.gv')


def test_from_single_statement_module():
    ast_root = ast.parse("A = 1")
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 1
    graph.to_graphviz().render(sys._getframe().f_code.co_name + '.gv')


def test_from_two_statement_module():
    ast_root = ast.parse("A = 1; B = 2")
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 2
    graph.to_graphviz().render(sys._getframe().f_code.co_name + '.gv')


def test_simple_conditional():
    ast_root = ast.parse(textwrap.dedent("""
    if a is not None:
        print(a.b)
    else:
        print(None)
    """))
    graph = FlowGraph.from_ast(ast_root)
    assert graph.statement_count == 4
    graph.to_graphviz().render(sys._getframe().f_code.co_name + '.gv')


def test_self_graph():
    import flow.graph
    with open(flow.graph.__file__) as fd:
        module = fd.read()
    ast_root = ast.parse(module, flow.graph.__name__)
    graph = FlowGraph.from_ast(ast_root)
    graph.to_graphviz().render(sys._getframe().f_code.co_name + '.gv')
