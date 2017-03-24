import ast
import collections
import functools

import graphviz
import astunparse


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


class ImplicitReturnStmt(ast.stmt):
    pass


@functools.singledispatch
def flow_graph_from_ast(ast_node, expand=False, func_returns=[], loop_breaks=[]):
    raise NotImplementedError


@flow_graph_from_ast.register(ast.stmt)
def _(ast_node, expand=False, func_returns=[], loop_breaks=[]):
    graph = FlowGraph()
    statement = graph.add_statement_node(ast_node)
    graph.add_edge(graph.start_node, statement)
    graph.add_edge(statement, graph.end_node)
    return graph


@flow_graph_from_ast.register(list)
def _(ast_list, expand=False, func_returns=[], loop_breaks=[]):
    graph = FlowGraph()
    graph.add_edge(graph.start_node, graph.end_node)
    for ast_node in ast_list:
        graph.insert(flow_graph_from_ast(ast_node, expand, func_returns, loop_breaks), graph.end_node)
    return graph


@flow_graph_from_ast.register(ast.Module)
def _(ast_root, expand=False, func_returns=[], loop_breaks=[]):
    return flow_graph_from_ast(ast_root.body)


@flow_graph_from_ast.register(ast.FunctionDef)
@flow_graph_from_ast.register(ast.AsyncFunctionDef)
def _(ast_root, expand=False, func_returns=[], loop_breaks=[]):
    if expand:
        func_returns.append(set())
        graph = flow_graph_from_ast(ast_root.body + [ImplicitReturnStmt()], expand, func_returns, loop_breaks)
        returns = func_returns.pop()
        for return_ in returns:
            graph.add_edge(return_, graph.end_node)

        return graph
    else:
        return flow_graph_from_ast.registry[ast.stmt](ast_root, expand, func_returns, loop_breaks)


@flow_graph_from_ast.register(ast.While)
@flow_graph_from_ast.register(ast.For)
def _(ast_loop, expand=False, func_returns=[], loop_breaks=[]):
    loop_breaks.append(set())
    graph = FlowGraph()
    decision_loop = graph.add_decision_node(ast_loop)
    merge_loop = graph.add_merge_node()
    graph.add_edge(graph.start_node, decision_loop)
    graph.add_edge(decision_loop, graph.end_node)
    graph.add_edge(merge_loop, graph.end_node)
    graph.embed(flow_graph_from_ast(ast_loop.body, expand, func_returns, loop_breaks),
                start_node=decision_loop, end_node=decision_loop)
    modifiers = loop_breaks.pop()
    for mod in modifiers:
        if isinstance(mod.statement, ast.Continue):
            graph.add_edge(mod, decision_loop)
        else:  # break
            graph.add_edge(mod, merge_loop)

    return graph


@flow_graph_from_ast.register(ast.Break)
@flow_graph_from_ast.register(ast.Continue)
def _(ast_break_continue, expand=False, func_returns=[], loop_breaks=[]):
    graph = flow_graph_from_ast.registry[ast.stmt](ast_break_continue)
    assert len(graph.user_nodes) == 1
    break_continue_node = next(iter(graph.user_nodes))
    graph.edges[break_continue_node].clear()
    loop_breaks[-1].add(break_continue_node)
    return graph


@flow_graph_from_ast.register(ast.Return)
def _(ast_return, expand=False, func_returns=[], loop_breaks=[]):
    graph = flow_graph_from_ast.registry[ast.stmt](ast_return)
    assert len(graph.user_nodes) == 1
    return_node = next(iter(graph.user_nodes))
    graph.edges[return_node].clear()
    func_returns[-1].add(return_node)
    return graph


@flow_graph_from_ast.register(ast.If)
def _(ast_if, expand=False, func_returns=[], loop_breaks=[]):
    graph = FlowGraph()
    decision_if = graph.add_decision_node(ast_if)
    merge_if = graph.add_merge_node()
    graph.add_edge(graph.start_node, decision_if)
    graph.add_edge(merge_if, graph.end_node)
    graph.embed(flow_graph_from_ast(ast_if.body, expand, func_returns, loop_breaks),
                start_node=decision_if, end_node=merge_if)
    if ast_if.orelse:
        graph.embed(flow_graph_from_ast(ast_if.orelse, expand, func_returns, loop_breaks),
                    start_node=decision_if, end_node=merge_if)
    else:
        graph.add_edge(decision_if, merge_if)

    return graph


class FlowGraph:
    def __init__(self):
        self.start_node = StartNode()
        self.end_node = StopNode()
        self.user_nodes = set()
        self.implicit_nodes = set()
        self.edges = collections.defaultdict(set)

    @property
    def statement_count(self):
        return sum(1 for n in self.user_nodes if n.statement is not None and not isinstance(n.statement, ImplicitReturnStmt))

    @property
    def returns_implicitly(self):
        implicit_return_node = next((node for node in self.implicit_nodes if
                                    isinstance(node.statement, ImplicitReturnStmt)), None)
        if implicit_return_node is None:
            return False
        return any(implicit_return_node in self.edges[from_node] for from_node in self.edges)

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
            if len(from_nodes) > 1:
                continue
            elif not from_nodes:
                # this is more like W/A than solution
                # something about break/continue/return is not cleaner properly
                del self.edges[node]
                self.user_nodes.remove(node)
                return self.reduce_merge_nodes()  # recursion here is quite ugly

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

        font_attr = {'fontname': 'Courier', 'fontsize': '9'}
        dot = graphviz.Digraph(format='png', graph_attr=font_attr,
                               node_attr=font_attr, edge_attr=font_attr)
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
        elif isinstance(node.statement, ImplicitReturnStmt):
            return '[return None]'
        elif isinstance(node, DecisionNode):
            if isinstance(node.statement, ast.If):
                return 'if {}'.format(astunparse.unparse(node.statement.test))
            elif isinstance(node.statement, ast.While):
                return 'while {}'.format(astunparse.unparse(node.statement.test))
            elif isinstance(node.statement, ast.For):
                return 'for {} in {}'.format(astunparse.unparse(node.statement.target),
                                             astunparse.unparse(node.statement.iter))
            else:
                return '?'
        return astunparse.unparse(node.statement)
