# RAG Pipeline Overview

This document describes the processing flow for the RAG components under src/rag.

## What It Does

The pipeline loads Markdown docs from data/knowledge, splits them into chunks with light metadata, indexes them in two ways (BM25 and dense embeddings), and then uses a hybrid retrieval + rerank strategy to answer queries.

## Data Flow

1) Document loading
- Source: data/knowledge/**/*.md
- Loader: src/rag/doc_loader.py
- Output: list of {source, content}

2) Chunking
- Split by Markdown heading into sections.
- Chunk each section by max length with overlap.
- Augment each chunk with metadata headers (title, section, image captions).
- Builder: src/rag/chunking.py
- Output: list of Chunk objects (id, text, source, title, section, image_captions)

3) Indexing
- Sparse index: BM25 over chunk text (rank_bm25).
- Dense index: ChromaDB + embeddings via vLLM API.
- Sparse: src/rag/bm25_index.py
- Dense: src/rag/chroma_store.py

4) Retrieval
- Dense retrieve top-K using embeddings (ChromaDB).
- Sparse retrieve top-K using BM25.
- Fuse ranked lists with RRF (reciprocal rank fusion).
- Optional rerank with CrossEncoder (sentence_transformers).
- Pipeline: src/rag/pipeline.py

5) Fallback
- If the pipeline raises any exception, fallback to a simple token match over raw docs.
- Entry: src/rag/retrieve.py

## Key Modules

- src/rag/doc_loader.py
  Reads Markdown docs from data/knowledge and returns raw text.

- src/rag/chunking.py
  Splits docs into chunk objects, adds title/section/image metadata.

- src/rag/bm25_index.py
  BM25 sparse retriever for lexical matching.

- src/rag/chroma_store.py
  Dense retriever using ChromaDB + vLLM embeddings.

- src/rag/pipeline.py
  Hybrid retrieval (dense + sparse), fusion, and rerank.

- src/rag/retrieve.py
  Entry point with fallback to a simple retriever.

## Runtime Requirements

- Python packages: requests, chromadb, rank_bm25, sentence_transformers
- A vLLM server available at config.vllm.base_url
- A model available at config.vllm.model_name
- A rerank model at config.rag_rerank_model
- Local data directory: data/knowledge with Markdown files
- A writable Chroma persistence folder (default: data/chroma)

## Known Run Blockers

- The code imports src.config, but there is no src/config.py in this repo.
  This must be added or the import changed to use the top-level config.py.
- If the vLLM endpoint or model is missing, dense retrieval will fail.
- If required packages are not installed, imports will fail at runtime.

## Typical Usage

- Use rag_retrieve(query) from src/rag/retrieve.py
  It will run the pipeline and fallback to simple retrieval if needed.

## Tuning Knobs (from config)

- rag_chunk_max_chars
- rag_chunk_overlap
- rag_dense_k
- rag_sparse_k
- rag_rrf_k
- rag_rerank_k
- rag_rerank_model
- vllm.base_url
- vllm.model_name
