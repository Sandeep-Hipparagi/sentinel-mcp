"""Graph memory tests: SQLite fallback round-trips, depth, idempotence."""

from pathlib import Path

from sentinel_mcp.schemas import MemoryEdgeInput, MemoryQueryInput, MemoryUpsertInput
from sentinel_mcp.tools.graph_memory import GraphMemory


class TestSqliteBackend:
    def test_backend_is_observable(self, tmp_path: Path):
        mem = GraphMemory(sqlite_path=tmp_path / "m.db")
        assert mem.backend in {"sqlite", "falkordb"}
        mem.close()

    def test_upsert_query_roundtrip(self, tmp_path: Path):
        mem = GraphMemory(sqlite_path=tmp_path / "m.db")
        mem.upsert_node(
            MemoryUpsertInput(node_id="svc-a", labels=["Service"], properties={"tier": 1})
        )
        mem.upsert_node(MemoryUpsertInput(node_id="svc-b", labels=["Service"], properties={}))
        mem.add_edge(MemoryEdgeInput(src="svc-a", relation="DEPENDS_ON", dst="svc-b"))
        out = mem.query_neighbors(MemoryQueryInput(node_id="svc-a", max_depth=1))
        assert out.backend == "sqlite"
        assert {n["id"] for n in out.nodes} == {"svc-a", "svc-b"}
        assert any(e["relation"] == "DEPENDS_ON" for e in out.edges)
        mem.close()

    def test_upsert_is_idempotent(self, tmp_path: Path):
        mem = GraphMemory(sqlite_path=tmp_path / "m.db")
        for _ in range(3):
            mem.upsert_node(MemoryUpsertInput(node_id="n1", labels=["A"], properties={"k": "v"}))
        out = mem.query_neighbors(MemoryQueryInput(node_id="n1", max_depth=1))
        assert len([n for n in out.nodes if n["id"] == "n1"]) == 1
        mem.close()

    def test_depth_limits_traversal(self, tmp_path: Path):
        mem = GraphMemory(sqlite_path=tmp_path / "m.db")
        for i in range(4):
            mem.upsert_node(MemoryUpsertInput(node_id=f"n{i}"))
        for i in range(3):
            mem.add_edge(MemoryEdgeInput(src=f"n{i}", relation="NEXT", dst=f"n{i + 1}"))
        shallow = mem.query_neighbors(MemoryQueryInput(node_id="n0", max_depth=1))
        deep = mem.query_neighbors(MemoryQueryInput(node_id="n0", max_depth=3))
        assert {n["id"] for n in shallow.nodes} == {"n0", "n1"}
        assert {n["id"] for n in deep.nodes} == {"n0", "n1", "n2", "n3"}
        mem.close()

    def test_empty_graph_returns_queried_node(self, tmp_path: Path):
        mem = GraphMemory(sqlite_path=tmp_path / "m.db")
        out = mem.query_neighbors(MemoryQueryInput(node_id="ghost", max_depth=2))
        assert out.backend == "sqlite"
        assert any(n["id"] == "ghost" for n in out.nodes)
        mem.close()

    def test_persistence_across_connections(self, tmp_path: Path):
        p = tmp_path / "m.db"
        mem1 = GraphMemory(sqlite_path=p)
        mem1.upsert_node(MemoryUpsertInput(node_id="persist", labels=[], properties={"x": 1}))
        mem1.close()
        mem2 = GraphMemory(sqlite_path=p)
        out = mem2.query_neighbors(MemoryQueryInput(node_id="persist", max_depth=1))
        assert any(n["id"] == "persist" and n["properties"] == {"x": 1} for n in out.nodes)
        mem2.close()

    def test_edge_idempotence(self, tmp_path: Path):
        mem = GraphMemory(sqlite_path=tmp_path / "m.db")
        mem.upsert_node(MemoryUpsertInput(node_id="a"))
        mem.upsert_node(MemoryUpsertInput(node_id="b"))
        for _ in range(3):
            mem.add_edge(MemoryEdgeInput(src="a", relation="LINKS", dst="b"))
        out = mem.query_neighbors(MemoryQueryInput(node_id="a", max_depth=1))
        assert len(out.edges) == 1
        mem.close()
