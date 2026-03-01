# src/merkaba/memory/vectors.py
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


@dataclass
class VectorMemory:
    """ChromaDB-backed vector memory for semantic search."""

    persist_dir: str = field(
        default_factory=lambda: os.path.expanduser("~/.merkaba/memory_vectors/")
    )
    ollama_model: str = "nomic-embed-text"
    _client: Any = field(default=None, init=False, repr=False)
    _embedding_fn: Any = field(default=None, init=False, repr=False)
    _collections: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        if not HAS_CHROMADB:
            raise ImportError(
                "chromadb is required for VectorMemory. Install with: pip install chromadb"
            )
        os.makedirs(self.persist_dir, exist_ok=True)
        self._embedding_fn = OllamaEmbeddingFunction(
            model_name=self.ollama_model,
            url="http://localhost:11434/api/embeddings",
        )
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._init_collections()

    def _init_collections(self):
        for name in ("facts", "decisions", "learnings"):
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                embedding_function=self._embedding_fn,
            )

    def _collection(self, name: str):
        return self._collections[name]

    # --- Indexing ---

    def index_fact(self, fact_id: int, business_id: int, text: str) -> None:
        self._collection("facts").upsert(
            ids=[str(fact_id)],
            documents=[text],
            metadatas=[{"business_id": business_id}],
        )

    def index_decision(self, decision_id: int, business_id: int, text: str) -> None:
        self._collection("decisions").upsert(
            ids=[str(decision_id)],
            documents=[text],
            metadatas=[{"business_id": business_id}],
        )

    def index_learning(self, learning_id: int, text: str) -> None:
        self._collection("learnings").upsert(
            ids=[str(learning_id)],
            documents=[text],
        )

    # --- Deletion ---

    def delete_vectors(self, collection_name: str, ids: list[str]) -> None:
        """Remove vectors by ID from a collection."""
        if not ids:
            return
        collection = self._collection(collection_name)
        collection.delete(ids=ids)

    # --- Rebuild ---

    def rebuild_from_store(self, store) -> dict:
        """Rebuild all vector collections from non-archived SQLite data.

        Drops and recreates collections, then re-indexes everything.
        Returns {"facts": N, "decisions": N, "learnings": N}.
        """
        stats = {"facts": 0, "decisions": 0, "learnings": 0}

        for name in ("facts", "decisions", "learnings"):
            self._client.delete_collection(name)
        self._init_collections()

        businesses = store.list_businesses()
        business_ids = [0] + [b["id"] for b in businesses]
        for bid in business_ids:
            for fact in store.get_facts(bid, include_archived=False):
                text = f"{fact['category']}: {fact['key']} = {fact['value']}"
                self.index_fact(fact["id"], bid, text)
                stats["facts"] += 1

            for dec in store.get_decisions(bid, include_archived=False):
                text = f"{dec['decision']} -- {dec['reasoning']}"
                self.index_decision(dec["id"], bid, text)
                stats["decisions"] += 1

        for learn in store.get_learnings(include_archived=False):
            self.index_learning(learn["id"], learn["insight"])
            stats["learnings"] += 1

        logger.info("Vector rebuild complete: %s", stats)
        return stats

    # --- Search ---

    def search_facts(
        self, query: str, business_id: int | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        where = {"business_id": business_id} if business_id else None
        results = self._collection("facts").query(
            query_texts=[query],
            n_results=limit,
            where=where,
        )
        return self._format_results(results)

    def search_decisions(
        self, query: str, business_id: int | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        where = {"business_id": business_id} if business_id else None
        results = self._collection("decisions").query(
            query_texts=[query],
            n_results=limit,
            where=where,
        )
        return self._format_results(results)

    def search_learnings(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        results = self._collection("learnings").query(
            query_texts=[query],
            n_results=limit,
        )
        return self._format_results(results)

    def _format_results(self, results: dict) -> list[dict[str, Any]]:
        if not results.get("ids") or not results["ids"][0]:
            return []
        ids = results["ids"][0]
        docs = results.get("documents", [[]])[0] if results.get("documents") else []
        dists = results.get("distances", [[]])[0] if results.get("distances") else []
        metas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
        formatted = []
        for i, id_ in enumerate(ids):
            try:
                parsed_id = int(id_)
            except (ValueError, TypeError):
                continue
            entry = {
                "id": parsed_id,
                "text": docs[i] if i < len(docs) else "",
                "distance": dists[i] if i < len(dists) else None,
            }
            if i < len(metas) and metas[i]:
                entry["metadata"] = metas[i]
            formatted.append(entry)
        return formatted

    def close(self):
        self._client = None
        self._collections = {}
