"""Graph algorithms for topology validation.

Implements Johnson's algorithm for finding all simple cycles in a directed graph,
along with helper functions for strongly connected components.

References:
    Donald B Johnson. "Finding all the elementary circuits of a directed graph."
    SIAM Journal on Computing. 1975.
"""

from collections import defaultdict
from collections.abc import Generator


def simple_cycles(graph: dict[str, set[str]]) -> Generator[list[str], None, None]:
    """Find all simple cycles in a directed graph using Johnson's algorithm.

    Args:
        graph: A dictionary mapping each vertex to a set of its neighbours.

    Yields:
        Each elementary cycle as a list of vertices.
    """
    graph = {v: set(nbrs) for v, nbrs in graph.items()}
    sccs = _strongly_connected_components(graph)
    while sccs:
        scc = sccs.pop()
        startnode = scc.pop()
        path = [startnode]
        blocked: set[str] = set()
        closed: set[str] = set()
        blocked.add(startnode)
        B: dict[str, set[str]] = defaultdict(set)
        stack: list[tuple[str, list[str]]] = [(startnode, list(graph[startnode]))]
        while stack:
            thisnode, nbrs = stack[-1]
            if nbrs:
                nextnode = nbrs.pop()
                if nextnode == startnode:
                    yield path[:]
                    closed.update(path)
                elif nextnode not in blocked:
                    path.append(nextnode)
                    stack.append((nextnode, list(graph[nextnode])))
                    closed.discard(nextnode)
                    blocked.add(nextnode)
                    continue
            if not nbrs:
                if thisnode in closed:
                    _unblock(thisnode, blocked, B)
                else:
                    for nbr in graph[thisnode]:
                        if thisnode not in B[nbr]:
                            B[nbr].add(thisnode)
                stack.pop()
                path.pop()
        _remove_node(graph, startnode)
        H = _subgraph(graph, set(scc))
        sccs.extend(_strongly_connected_components(H))


def _unblock(thisnode: str, blocked: set[str], B: dict[str, set[str]]) -> None:
    """Unblock a node and recursively unblock nodes in its B set."""
    stack = {thisnode}
    while stack:
        node = stack.pop()
        if node in blocked:
            blocked.remove(node)
            stack.update(B[node])
            B[node].clear()


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[set[str]]:
    """Find all strongly connected components using Tarjan's algorithm.

    Args:
        graph: A dictionary mapping each vertex to a set of its neighbours.

    Returns:
        A list of sets, each containing the vertices of a strongly connected component.
    """
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    result: list[set[str]] = []

    def _strong_connect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)

        for successor in graph.get(node, set()):
            if successor not in index:
                _strong_connect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif successor in stack:
                lowlink[node] = min(lowlink[node], index[successor])

        if lowlink[node] == index[node]:
            connected_component: set[str] = set()
            while True:
                successor = stack.pop()
                connected_component.add(successor)
                if successor == node:
                    break
            result.append(connected_component)

    for node in graph:
        if node not in index:
            _strong_connect(node)

    return result


def _remove_node(graph: dict[str, set[str]], target: str) -> None:
    """Remove a node and all its edges from the graph."""
    del graph[target]
    for nbrs in graph.values():
        nbrs.discard(target)


def _subgraph(graph: dict[str, set[str]], vertices: set[str]) -> dict[str, set[str]]:
    """Get the subgraph induced by a set of vertices."""
    return {v: graph[v] & vertices for v in vertices}
