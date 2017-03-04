import ast
import collections
import functools

import graphviz


class Node:
    __slots__ = ("statement",)

    def __init__(self, statement):
        self.statement = statement

    def __str__(self):
        return "<{0} of stmt {1}>".format(type(self).__name__,
                                          type(self.statement).__name__)


class StartNode(Node):
    def __init__(self, statement=None):
        super(StartNode, self).__init__(statement)


class StopNode(Node):
    def __init__(self, statement=None):
        super(StopNode, self).__init__(statement)


class DecisionNode(Node):
    pass


class MergeNode(Node):
    pass

@functools.singledispatch
def flow_graph_from_ast(ast_node):
    graph = FlowGraph()
    statement = graph.add_statement(ast_node)
    graph.add_edge(graph.start_node, statement)
    graph.add_edge(statement, graph.end_node)
    return graph


@flow_graph_from_ast.register(list)
def _(ast_list):
    graph = FlowGraph()
    current_exec_point = graph.start_node
    if not ast_list:
        graph.add_edge(graph.start_node, graph.end_node)
    else:
        for ast_node in ast_list:
            graph.embed(flow_graph_from_ast(ast_node),
                        start_node=current_exec_point, end_node=graph.end_node)
            current_exec_point = graph.end_node
    return graph


@flow_graph_from_ast.register(ast.Module)
@flow_graph_from_ast.register(ast.FunctionDef)
@flow_graph_from_ast.register(ast.AsyncFunctionDef)
def _(ast_root):
    return flow_graph_from_ast(ast_root.body)


@flow_graph_from_ast.register(ast.If)
def _(ast_if):
    graph = FlowGraph()
    decision_if = graph.add_node(DecisionNode(ast_if))
    merge_if = graph.add_node(MergeNode(ast_if))
    graph.add_edge(graph.start_node, decision_if)
    graph.add_edge(merge_if, graph.end_node)
    graph.embed(flow_graph_from_ast(ast_if.body),
                start_node=decision_if, end_node=merge_if)
    if ast_if.orelse:
        graph.embed(flow_graph_from_ast(ast_if.orelse),
                    start_node=decision_if, end_node=merge_if)
    else:
        graph.add_edge(decision_if, merge_if)

    return graph


class FlowGraph:
    def __init__(self):
        self.start_node = StartNode()
        self.end_node = StopNode()
        self.statements = []
        self.edges = collections.defaultdict(set)

    @property
    def statement_count(self):
        return len(self.statements)

    def add_statement(self, ast_node):
        statement = Node(ast_node)
        self.statements.append(statement)
        return statement

    def add_node(self, node):
        self.statements.append(node)
        return node

    def embed(self, other_graph, start_node, end_node):
        self.statements.extend(other_graph.statements)
        for from_edge in other_graph.edges:
            to_nodes = other_graph.edges[from_edge]
            if other_graph.end_node in to_nodes:
                to_nodes = (to_nodes | {end_node}) - {other_graph.end_node}
            if other_graph.start_node in to_nodes:
                to_nodes = (to_nodes | {start_node}) - {other_graph.start_node}
            if from_edge == other_graph.start_node:
                from_edge = start_node
            self.edges[from_edge].update(to_nodes)

    def add_edge(self, from_node, to_node):
        self.edges[from_node].add(to_node)

    @classmethod
    def from_ast(cls, ast_root):
        return flow_graph_from_ast(ast_root)

    def to_graphviz(self):
        def add_node(dot, node, **kwargs):
            return dot.node(str(id(node)), **kwargs)

        def add_edge(dot, from_node, to_node, **kwargs):
            return dot.edge(str(id(from_node)), str(id(to_node)), **kwargs)

        dot = graphviz.Digraph()
        add_node(dot, self.start_node, shape='circle', label='')
        add_node(dot, self.end_node, shape='circle', style='filled', label='')
        for s in self.statements:
            n = add_node(dot, node=s, label=str(s), shape='diamond' if isinstance(s, DecisionNode) else 'rect')

        for from_node in self.edges:
            for to_node in self.edges[from_node]:
                add_edge(dot, from_node, to_node)

        return dot
