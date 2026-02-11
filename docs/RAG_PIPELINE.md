# RAG Pipeline 说明

本文件说明 src/rag 目录下各模块的关系，以及当前 RAG 的处理流程。

## 文件关系

- src/rag/types.py
  定义 Chunk 数据结构，所有模块共享。

- src/rag/doc_loader.py
  从 data/knowledge 读取 Markdown 文档，产出 {source, content} 列表。

- src/rag/chunking.py
  按标题分节并切块，补齐标题、章节、图片说明等元信息，生成 Chunk。

- src/rag/bm25_index.py
  BM25 稀疏检索（词法相关性）。

- src/rag/chroma_store.py
  ChromaDB 稠密检索，使用 vLLM embedding 接口生成向量并建立持久化索引。

- src/rag/pipeline.py
  组合检索入口：稠密 + 稀疏融合（RRF）+ 交叉编码器重排。

- src/rag/retrieve.py
  统一调用入口，失败时回退到简单词匹配检索。


src/llamaindex_rag/llamaindex_rag.py 另一条 RAG 路线：LlamaIndex + ChromaVectorStore，用独立持久化目录 data/chroma_llamaindex。



## RAG 流程

1. 文档加载
   由 doc_loader.load_docs() 读取 data/knowledge/**/*.md。

2. 切分与增强
   chunking.build_chunks() 先按标题分节，再按长度切块，并补上标题/章节/图片说明。

3. 稠密检索（Dense）
   chroma_store.dense_retrieve() 负责向量检索。若索引为空则先 build_index()。

4. 稀疏检索（Sparse）
   bm25_index.BM25Index.search() 负责关键词相关性检索。

5. 融合排序
   pipeline._rrf_fuse() 对稠密与稀疏结果做 RRF 融合。

6. 重排
   pipeline._rerank() 使用 sentence_transformers 的 CrossEncoder 重新排序候选。

7. 返回结果
   pipeline.retrieve() 输出前 k 个 {source, content}。

8. 回退逻辑
   retrieve.rag_retrieve() 捕获异常后回退到 simple_retrieve()。

## 关键入口

- 对外调用：src/rag/retrieve.py 中的 rag_retrieve(query, k)
- 管道实现：src/rag/pipeline.py 中的 RagPipeline

## 依赖与配置

- 依赖包：requests、chromadb、rank_bm25、sentence_transformers
- 稠密检索 embedding 使用 config.vllm_chat（见 chroma_store.py）
- 交叉编码器重排使用 config.rag.rerank_model
- 切块参数：config.rag.chunk_max_chars、config.rag.chunk_overlap
- 检索参数：config.rag.dense_k、config.rag.sparse_k、config.rag.rrf_k、config.rag.rerank_k
- 索引目录：data/chroma（默认持久化目录）




src/llamaindex_rag/llamaindex_rag.py 另一条 RAG 路线：LlamaIndex + ChromaVectorStore，用独立持久化目录 data/chroma_llamaindex。