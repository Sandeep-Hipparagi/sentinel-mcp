"""Graph memory tools: FalkorDB backend with automatic embedded SQLite fallback.

The active backend is always observable via `MemoryQueryOutput.backend`.
The SQLite backend is deterministic and dependency-free, so the server boots
and serves memory tools in every environment.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from sentinel_mcp.schemas import (
    MemoryEdgeInput,
    MemoryQueryInput,
    MemoryQueryOutput,
    MemoryUpsertInput,
)


class GraphMemory:
    """Unified graph-memory facade over FalkorDB or SQLite."""

    def __init__(self, sqlite_path: str | Path = "sentinel_memory.db") -> None:
        self._sqlite_path = Path(sqlite_path)
        self._conn: sqlite3.Connection | None = None
        self._falkor: Any = None
        self._graph: Any = None
        self._init_sqlite()
        self._try_falkordb()

    # -- backend plumbing ---------------------------------------------------

    def _init_sqlite(self) -> None:
        self._conn = sqlite3.connect(self._sqlite_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS nodes ("
            " node_id TEXT PRIMARY KEY, labels TEXT NOT NULL DEFAULT '[]', "
            "properties TEXT NOT NULL DEFAULT '{}')"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS edges ("
            " src TEXT NOT NULL, relation TEXT NOT NULL, dst TEXT NOT NULL, "
            "PRIMARY KEY (src, relation, dst))"
        )
        self._conn.commit()

    def _try_falkordb(self) -> None:
        """Attach FalkorDB when reachable; stay silent otherwise."""
        try:
            from falkordb import FalkorDB  # noqa: PLC0415
        except ImportError:
            return
        try:
            db = FalkorDB(host="localhost", port=6379)
            db.connection.ping()
            self._falkor = db
            self._graph = db.select_graph("sentinel_memory")
        except Exception:
            self._falkor = None
            self._graph = None

    @property
    def backend(self) -> str:
        return "falkordb" if self._falkor is not None else "sqlite"

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- operations ----------------------------------------------------------

    def upsert_node(self, payload: MemoryUpsertInput) -> dict[str, Any]:
        if self._falkor is not None:
            import json as _json  # noqa: PLC0415

            props = _json.dumps(payload.properties, sort_keys=True)
            self._graph.query(
                "MERGE (n:Node {id: $id}) SET n.labels = $labels, n.properties = $props",
                {"id": payload.node_id, "labels": payload.labels, "props": props},
            )
            return {"backend": "falkordb", "node_id": payload.node_id}
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO nodes (node_id, labels, properties) VALUES (?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET labels = excluded.labels, "
            "properties = excluded.properties",
            (
                payload.node_id,
                json.dumps(payload.labels, sort_keys=True),
                json.dumps(payload.properties, sort_keys=True),
            ),
        )
        self._conn.commit()
        return {"backend": "sqlite", "node_id": payload.node_id}

    def add_edge(self, payload: MemoryEdgeInput) -> dict[str, Any]:
        if self._falkor is not None:
            self._graph.query(
                f"MATCH (a:Node {{id: $src}}), (b:Node {{id: $dst}}) "  # noqa: S608 (no user SQL)
                f"MERGE (a)-[:{payload.relation}]->(b)",
                {"src": payload.src, "dst": payload.dst},
            )
            return {
                "backend": "falkordb",
                "edge": f"{payload.src}-[{payload.relation}]->{payload.dst}",
            }
        assert self._conn is not None
        self._conn.execute(
            "INSERT OR IGNORE INTO edges (src, relation, dst) VALUES (?, ?, ?)",
            (payload.src, payload.relation, payload.dst),
        )
        self._conn.commit()
        return {"backend": "sqlite", "edge": f"{payload.src}-[{payload.relation}]->{payload.dst}"}

    def query_neighbors(self, payload: MemoryQueryInput) -> MemoryQueryOutput:
        if self._falkor is not None:
            return self._query_falkordb(payload)
        return self._query_sqlite(payload)

    def _query_falkordb(self, payload: MemoryQueryInput) -> MemoryQueryOutput:
        assert self._graph is not None
        res = self._graph.query(
            "MATCH p = (start:Node {id: $id})-[*1.." + str(payload.max_depth) + "]-(n) "
            "RETURN nodes(p), relationships(p)",
            {"id": payload.node_id},
        )
        nodes: list[dict[str, Any]] = []
        seen_nodes: set[int] = set()
        edges: list[dict[str, Any]] = []
        seen_edges: set[int] = set()
        for row in res.result_set or []:
            for node in row[0]:
                if node.id not in seen_nodes:
                    seen_nodes.add(node.id)
                    nodes.append(
                        {
                            "id": node.properties.get("id", str(node.id)),
                            "labels": list(node.labels or []),
                        }
                    )
            for edge in row[1]:
                if edge.id not in seen_edges:
                    seen_edges.add(edge.id)
                    edges.append(
                        {
                            "relation": edge.relation,
                            "src": str(edge.src_node),
                            "dst": str(edge.dest_node),
                        }
                    )
        return MemoryQueryOutput(backend="falkordb", nodes=nodes, edges=edges)

    def _query_sqlite(self, payload: MemoryQueryInput) -> MemoryQueryOutput:
        assert self._conn is not None
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()

        frontier = {payload.node_id}
        for _ in range(payload.max_depth):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            rows = self._conn.execute(
                f"SELECT src, relation, dst FROM edges "  # noqa: S608
                f"WHERE src IN ({placeholders}) OR dst IN ({placeholders})",
                list(frontier) + list(frontier),
            ).fetchall()
            next_frontier: set[str] = set()
            for src, relation, dst in rows:
                key = (src, relation, dst)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"src": src, "relation": relation, "dst": dst})
                next_frontier.update((src, dst))
            frontier = next_frontier - seen_nodes
        seen_nodes.update(frontier)

        wanted = seen_nodes | {payload.node_id}
        placeholders = ",".join("?" for _ in wanted) or "''"
        for node_id, labels, properties in self._conn.execute(
            f"SELECT node_id, labels, properties FROM nodes "  # noqa: S608
            f"WHERE node_id IN ({placeholders})",
            list(wanted) or [""],
        ).fetchall():
            nodes.append(
                {"id": node_id, "labels": json.loads(labels), "properties": json.loads(properties)}
            )
        if not nodes and payload.node_id not in seen_nodes:
            # Ensure the queried node appears even when the graph is empty.
            nodes.append({"id": payload.node_id, "labels": [], "properties": {}})
        return MemoryQueryOutput(backend="sqlite", nodes=nodes, edges=edges)
