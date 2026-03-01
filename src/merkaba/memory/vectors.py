# src/friday/memory/vectors.py
import os
from dataclasses import dataclass, field
from typing import Any

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
        default_factory=lambda: os.path.expanduser("~/.friday/memory_vectors/")
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
