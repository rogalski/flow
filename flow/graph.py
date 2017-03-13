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


class NonStatementNode(Node):
    def __init__(self, statement=None):
        super(NonStatementNode, self).__init__(statement)


class StartNode(NonStatementNode):
    pass


class StopNode(NonStatementNode):
    pass


class DecisionNode(Node):
    pass


class MergeNode(NonStatementNode):
    pass


@functools.singledispatch
def flow_graph_from_ast(ast_node, expand=False):
    graph = FlowGraph()
    statement = graph.add_statement_node(ast_node)
    graph.add_edge(graph.start_node, statement)
    graph.add_edge(statement, graph.end_node)
    return graph


@flow_graph_from_ast.register(list)
def _(ast_list, expand=False):
    graph = FlowGraph()
    graph.add_edge(graph.start_node, graph.end_node)
    for ast_node in ast_list:
        graph.insert(flow_graph_from_ast(ast_node), graph.end_node)
    return graph


@flow_graph_from_ast.register(ast.Module)
@flow_graph_from_ast.register(ast.FunctionDef)
@flow_graph_from_ast.register(ast.AsyncFunctionDef)
def _(ast_root, expand=False):
    if expand:
        return flow_graph_from_ast(ast_root.body)
    else:
        graph = FlowGraph()
        statement = graph.add_statement_node(ast_root)
        graph.add_edge(graph.start_node, statement)
        graph.add_edge(statement, graph.end_node)
        return graph


@flow_graph_from_ast.register(ast.If)
def _(ast_if, expand=False):
    graph = FlowGraph()
    decision_if = graph.add_decision_node(ast_if)
    merge_if = graph.add_merge_node()
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
        self.user_nodes = set()
        self.edges = collections.defaultdict(set)

    @property
    def statement_count(self):
        return sum(1 for n in self.user_nodes if n.statement is not None)

    @classmethod
    def from_ast(cls, ast_root):
        graph = flow_graph_from_ast(ast_root, expand=True)
        graph.reduce_merge_nodes()
        return graph

    def add_statement_node(self, ast_stmt_node):
        statement_node = Node(ast_stmt_node)
        self.user_nodes.add(statement_node)
        return statement_node

    def add_decision_node(self, ast_test_node):
        decision_node = DecisionNode(ast_test_node)
        self.user_nodes.add(decision_node)
        return decision_node

    def add_merge_node(self):
        merge_node = MergeNode()
        self.user_nodes.add(merge_node)
        return merge_node

    def add_edge(self, from_node, to_node):
        self.edges[from_node].add(to_node)

    def embed(self, other_graph, start_node, end_node):
        """Given two embed points, embed other flow graph in this graph"""
        self.user_nodes.update(other_graph.user_nodes)

        for edge_start in other_graph.edges:
            edge_stops = {s for s in other_graph.edges[edge_start]}

            if other_graph.end_node in edge_stops:
                edge_stops.remove(other_graph.end_node)
                edge_stops.add(end_node)
            if other_graph.start_node in edge_stops:
                edge_stops.remove(other_graph.start_node)
                edge_stops.add(start_node)

            if edge_start == other_graph.start_node:
                edge_start = start_node

            self.edges[edge_start].update(edge_stops)

    def insert(self, other_graph, insert_node):
        """Given single embed point, embed other flow graph in this graph"""
        start_node, end_node = self.insert_fake_merge_nodes(insert_node)
        self.embed(other_graph, start_node, end_node)

    def insert_fake_merge_nodes(self, insert_node):
        start_node = self.add_merge_node()
        end_node = self.add_merge_node()
        for from_node in list(self.edges):
            to_nodes = self.edges[from_node]
            if insert_node in to_nodes:
                to_nodes.remove(insert_node)
                to_nodes.add(start_node)
            if insert_node is from_node:
                self.edges[end_node] = self.edges.pop(insert_node)
        self.edges[end_node].add(insert_node)
        return start_node, end_node

    def reduce_merge_nodes(self):
        """If there are merge nodes with single incoming edge and single outgoing edge,
        it's removed and respective nodes are connected with simple edge"""

        for node in list(self.user_nodes):
            if not isinstance(node, MergeNode):
                continue
            to_nodes = self.edges[node]
            if len(to_nodes) != 1:
                continue
            from_nodes = [checked_node for checked_node in self.edges
                          if node in self.edges[checked_node]]
            if len(from_nodes) != 1:
                continue

            from_node = next(iter(from_nodes))
            to_node = next(iter(to_nodes))

            # remove node itself
            self.user_nodes.remove(node)

            # remove old connections
            self.edges[node].remove(to_node)
            self.edges[from_node].remove(node)

            # add new connection
            self.edges[from_node].add(to_node)

            return self.reduce_merge_nodes()  # recursion here is quite ugly

    def to_graphviz(self):
        def add_node(dot, node, **kwargs):
            return dot.node(str(id(node)), **kwargs)

        def add_edge(dot, from_node, to_node, **kwargs):
            return dot.edge(str(id(from_node)), str(id(to_node)), **kwargs)

        dot = graphviz.Digraph()
        add_node(dot, self.start_node, shape='circle', label='')
        add_node(dot, self.end_node, shape='doublecircle', label='')
        for node in self.user_nodes:
            add_node(dot, node=node,
                     label=self.get_graphviz_label(node),
                     shape=self.get_graphviz_shape(node))

        for from_node in self.edges:
            for to_node in self.edges[from_node]:
                add_edge(dot, from_node, to_node)

        return dot

    @staticmethod
    def get_graphviz_shape(node):
        if isinstance(node, (DecisionNode, MergeNode)):
            return 'diamond'
        return 'rect'

    @staticmethod
    def get_graphviz_label(node):
        if node.statement is None:
            return ''
        elif isinstance(node, DecisionNode):
            return str(node.statement.test)
        return str(node.statement)
