from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COLLECTION_INDEXER_SRC = ROOT / "tools" / "collection-indexer" / "src"
if str(COLLECTION_INDEXER_SRC) not in sys.path:
    sys.path.insert(0, str(COLLECTION_INDEXER_SRC))

from njupt_search_indexer.validate_sitegraph_index import main


if __name__ == "__main__":
    main()
