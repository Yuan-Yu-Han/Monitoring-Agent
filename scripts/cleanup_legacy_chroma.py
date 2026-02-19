#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path
import time

import chromadb

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.chroma_store import build_index

PERSIST = Path('rag_data/chroma').resolve()
LEGACY = {
    'rag_docs_chroma_builtin_no_trt',
    'rag_docs_chroma_builtin',
    'nomadpilot_docs',
    'nomadpilot_docs_chroma_builtin_no_trt',
    'nomadpilot_docs_chroma_builtin',
}


def main() -> int:
    client = chromadb.PersistentClient(path=str(PERSIST))
    before = {c.name for c in client.list_collections()}
    print('before:', sorted(before))

    deleted = []
    for name in sorted(LEGACY):
        if name in before:
            try:
                client.delete_collection(name)
                deleted.append(name)
            except Exception as exc:
                print(f'delete failed for {name}: {exc}')

    # 如果删除失败，回退到目录重建
    if any(name in {c.name for c in client.list_collections()} for name in LEGACY):
        ts = time.strftime('%Y%m%d_%H%M%S')
        backup = PERSIST.parent / f'chroma_backup_{ts}'
        print('fallback rebuild: moving', PERSIST, '->', backup)
        shutil.move(str(PERSIST), str(backup))
        PERSIST.mkdir(parents=True, exist_ok=True)
        build_index(str(PERSIST))
        client = chromadb.PersistentClient(path=str(PERSIST))

    after = {c.name for c in client.list_collections()}
    print('deleted:', deleted)
    print('after:', sorted(after))
    for c in client.list_collections():
        col = client.get_collection(c.name)
        print(f'{c.name}: {col.count()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
