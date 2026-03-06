# Context Engine Layout

- `intent_router.py`: LLM-first intent routing. Decides whether to retrieve:
  - event memory
  - chat memory
  - knowledge memory
- `retrievers.py`: concrete retrieval adapters for each memory type.
- `orchestrator.py`: executes routing plan and builds a unified context bundle.
- `memory/`: storage implementations used by context engine.
  - `case_memory.py`: JSONL store and lexical fallback retrieval.
  - `vector_memory.py`: Chroma-backed vector retrieval and write path.

Legacy imports under `src/memory/*` are compatibility wrappers only.
