# RAG (Knowledge Retrieval)

This repo currently uses the simplest reliable RAG shape for the knowledge base:

- Documents live under `backend/rag_data/knowledge/`.
- Index lives under `backend/rag_data/chroma/` (Chroma persistent store).
- Retrieval is **dense vector retrieval only** (no BM25 / no RRF / no reranking).

Entry point:

- `src.rag.retrieve.rag_retrieve()` calls `src.rag.chroma_store.retrieve()`.

Switch backend (optional):

- Default: `rag.knowledge_retriever = "chroma"`
- Use LlamaIndex: set `rag.knowledge_retriever = "llamaindex"` (or env `RAG_KNOWLEDGE_RETRIEVER=llamaindex`)

Notes:

- LlamaIndex implementation lives in `src.rag.llamaindex_rag` and uses its own persistent dir:
  `backend/rag_data/chroma_llamaindex/`.
