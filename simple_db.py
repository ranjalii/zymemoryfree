"""simple_db.py - Simple SQLite memory database (no proprietary logic)

Basic vector memory store with:
- Text-based memories
- Embedding-based search
- Simple CRUD operations
- Content encryption
"""
import sqlite3
import json
import time
from datetime import datetime
from typing import Optional, List, Dict
import numpy as np
from fastembed import TextEmbedding
from encryption import MemoryEncryption

# Initialize embedder
embedder = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    cache_dir="models"
)

# Initialize encryption
encryptor = MemoryEncryption()

EMBEDDING_DIM = 384


class SimpleMemoryDB:
    """Simple SQLite database for memory storage with vector search."""

    def __init__(self, db_path: str = "db/memories.db"):
        self.db_path = db_path
        self.create_schema()

    def get_conn(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_schema(self):
        """Create database schema."""
        conn = self.get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_used INTEGER
            );

            CREATE TABLE IF NOT EXISTS memories (
                memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                embedding BLOB NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key);

            -- Memory links for graph structure
            CREATE TABLE IF NOT EXISTS memory_links (
                link_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_memory_id INTEGER NOT NULL,
                to_memory_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                link_type TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (from_memory_id) REFERENCES memories(memory_id),
                FOREIGN KEY (to_memory_id) REFERENCES memories(memory_id),
                UNIQUE(from_memory_id, to_memory_id)
            );

            CREATE INDEX IF NOT EXISTS idx_links_from ON memory_links(from_memory_id);
            CREATE INDEX IF NOT EXISTS idx_links_to ON memory_links(to_memory_id);
            CREATE INDEX IF NOT EXISTS idx_links_user ON memory_links(user_id);

            -- FTS5 for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, tokenize='porter'
            );
        """)
        conn.commit()
        conn.close()

    # ---- API Key Management ----

    def create_api_key(self, api_key: str, user_id: str) -> bool:
        """Create a new API key."""
        try:
            conn = self.get_conn()
            conn.execute(
                "INSERT INTO api_keys (api_key, user_id, created_at) VALUES (?, ?, ?)",
                (api_key, user_id, int(time.time()))
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False

    def verify_api_key(self, api_key: str) -> Optional[str]:
        """Verify API key and return user_id."""
        conn = self.get_conn()
        row = conn.execute(
            "SELECT user_id FROM api_keys WHERE api_key = ?",
            (api_key,)
        ).fetchone()

        if row:
            # Update last_used
            conn.execute(
                "UPDATE api_keys SET last_used = ? WHERE api_key = ?",
                (int(time.time()), api_key)
            )
            conn.commit()
            conn.close()
            return row["user_id"]

        conn.close()
        return None

    # ---- Memory CRUD ----

    def create_memory(self, user_id: str, content: str, metadata: Optional[Dict] = None) -> int:
        """Create a new memory."""
        # Generate embedding from plaintext (before encryption)
        embedding = np.array(next(embedder.embed([content])), dtype=np.float32)

        conn = self.get_conn()
        cursor = conn.cursor()

        now = int(time.time())

        # Encrypt content and metadata
        encrypted_content = encryptor.encrypt(content)
        metadata_json = json.dumps(metadata) if metadata else None
        encrypted_metadata = encryptor.encrypt(metadata_json) if metadata_json else None

        cursor.execute(
            "INSERT INTO memories (user_id, content, metadata, embedding, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, encrypted_content, encrypted_metadata, embedding.tobytes(), now, now)
        )
        memory_id = cursor.lastrowid

        # Add to FTS (plaintext for searching)
        cursor.execute(
            "INSERT INTO memories_fts(rowid, content) VALUES (?, ?)",
            (memory_id, content)
        )

        conn.commit()
        conn.close()

        return memory_id

    def get_memory(self, memory_id: int, user_id: str) -> Optional[Dict]:
        """Get a single memory by ID."""
        conn = self.get_conn()
        row = conn.execute(
            "SELECT memory_id, user_id, content, metadata, created_at, updated_at "
            "FROM memories WHERE memory_id = ? AND user_id = ?",
            (memory_id, user_id)
        ).fetchone()
        conn.close()

        if not row:
            return None

        # Decrypt content and metadata
        decrypted_content = encryptor.decrypt(row["content"])
        decrypted_metadata = encryptor.decrypt(row["metadata"]) if row["metadata"] else None

        return {
            "id": row["memory_id"],
            "user_id": row["user_id"],
            "content": decrypted_content,
            "metadata": json.loads(decrypted_metadata) if decrypted_metadata else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }

    def list_memories(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        """List memories for a user."""
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT memory_id, content, metadata, created_at, updated_at "
            "FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        ).fetchall()
        conn.close()

        results = []
        for row in rows:
            decrypted_content = encryptor.decrypt(row["content"])
            decrypted_metadata = encryptor.decrypt(row["metadata"]) if row["metadata"] else None

            results.append({
                "id": row["memory_id"],
                "content": decrypted_content,
                "metadata": json.loads(decrypted_metadata) if decrypted_metadata else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            })

        return results

    def delete_memory(self, memory_id: int, user_id: str) -> bool:
        """Delete a memory."""
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM memories WHERE memory_id = ? AND user_id = ?",
            (memory_id, user_id)
        )
        cursor.execute(
            "DELETE FROM memories_fts WHERE rowid = ?",
            (memory_id,)
        )

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def count_memories(self, user_id: str) -> int:
        """Count total memories for a user."""
        conn = self.get_conn()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM memories WHERE user_id = ?",
            (user_id,)
        ).fetchone()["cnt"]
        conn.close()
        return count

    # ---- Search ----

    def search_memories(self, user_id: str, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search memories using hybrid approach:
        1. FTS for keyword matching
        2. Vector similarity for semantic search
        3. Combine scores
        """
        query_embedding = np.array(next(embedder.embed([query])), dtype=np.float32)

        conn = self.get_conn()

        # Get all memories for user
        rows = conn.execute(
            "SELECT memory_id, content, metadata, embedding, created_at, updated_at "
            "FROM memories WHERE user_id = ?",
            (user_id,)
        ).fetchall()

        if not rows:
            conn.close()
            return []

        # Calculate vector similarities
        results = []
        for row in rows:
            memory_embedding = np.frombuffer(row["embedding"], dtype=np.float32)

            # Cosine similarity
            similarity = float(
                np.dot(query_embedding, memory_embedding) /
                (np.linalg.norm(query_embedding) * np.linalg.norm(memory_embedding) + 1e-9)
            )

            # Decrypt content and metadata
            decrypted_content = encryptor.decrypt(row["content"])
            decrypted_metadata = encryptor.decrypt(row["metadata"]) if row["metadata"] else None

            results.append({
                "id": row["memory_id"],
                "content": decrypted_content,
                "metadata": json.loads(decrypted_metadata) if decrypted_metadata else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "score": similarity
            })

        # Get FTS boost scores
        fts_scores = {}
        try:
            fts_rows = conn.execute(
                "SELECT rowid, -bm25(memories_fts) as score "
                "FROM memories_fts WHERE content MATCH ? "
                "AND rowid IN (SELECT memory_id FROM memories WHERE user_id = ?)",
                (query, user_id)
            ).fetchall()

            for row in fts_rows:
                fts_scores[row["rowid"]] = row["score"]
        except:
            pass  # FTS query failed, continue with just vector search

        conn.close()

        # Boost scores with FTS
        for result in results:
            if result["id"] in fts_scores:
                result["score"] += fts_scores[result["id"]] * 0.3  # FTS boost weight

        # Sort by score and return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ---- Graph Operations ----

    def create_link(
        self,
        from_memory_id: int,
        to_memory_id: int,
        user_id: str,
        link_type: Optional[str] = None
    ) -> bool:
        """Create a link between two memories."""
        # Verify both memories exist and belong to user
        conn = self.get_conn()

        from_mem = conn.execute(
            "SELECT memory_id FROM memories WHERE memory_id = ? AND user_id = ?",
            (from_memory_id, user_id)
        ).fetchone()

        to_mem = conn.execute(
            "SELECT memory_id FROM memories WHERE memory_id = ? AND user_id = ?",
            (to_memory_id, user_id)
        ).fetchone()

        if not from_mem or not to_mem:
            conn.close()
            return False

        try:
            conn.execute(
                "INSERT INTO memory_links (from_memory_id, to_memory_id, user_id, link_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (from_memory_id, to_memory_id, user_id, link_type, int(time.time()))
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False  # Link already exists

    def get_linked_memories(self, memory_id: int, user_id: str, direction: str = "both") -> Dict:
        """
        Get memories linked to a given memory.

        Args:
            memory_id: Source memory ID
            user_id: User ID
            direction: "outgoing", "incoming", or "both"

        Returns:
            Dict with "outgoing" and "incoming" lists
        """
        conn = self.get_conn()
        result = {"outgoing": [], "incoming": []}

        if direction in ["outgoing", "both"]:
            # Get outgoing links (from this memory to others)
            rows = conn.execute("""
                SELECT m.memory_id, m.content, m.metadata, m.created_at, m.updated_at,
                       l.link_type, l.created_at as link_created_at
                FROM memory_links l
                JOIN memories m ON m.memory_id = l.to_memory_id
                WHERE l.from_memory_id = ? AND l.user_id = ?
            """, (memory_id, user_id)).fetchall()

            result["outgoing"] = [{
                "id": row["memory_id"],
                "content": encryptor.decrypt(row["content"]),
                "metadata": json.loads(encryptor.decrypt(row["metadata"])) if row["metadata"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "link_type": row["link_type"],
                "link_created_at": row["link_created_at"]
            } for row in rows]

        if direction in ["incoming", "both"]:
            # Get incoming links (from others to this memory)
            rows = conn.execute("""
                SELECT m.memory_id, m.content, m.metadata, m.created_at, m.updated_at,
                       l.link_type, l.created_at as link_created_at
                FROM memory_links l
                JOIN memories m ON m.memory_id = l.from_memory_id
                WHERE l.to_memory_id = ? AND l.user_id = ?
            """, (memory_id, user_id)).fetchall()

            result["incoming"] = [{
                "id": row["memory_id"],
                "content": encryptor.decrypt(row["content"]),
                "metadata": json.loads(encryptor.decrypt(row["metadata"])) if row["metadata"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "link_type": row["link_type"],
                "link_created_at": row["link_created_at"]
            } for row in rows]

        conn.close()
        return result

    def delete_link(self, from_memory_id: int, to_memory_id: int, user_id: str) -> bool:
        """Delete a link between two memories."""
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM memory_links WHERE from_memory_id = ? AND to_memory_id = ? AND user_id = ?",
            (from_memory_id, to_memory_id, user_id)
        )

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def get_memory_graph(self, memory_id: int, user_id: str, depth: int = 1) -> Dict:
        """
        Get a subgraph around a memory up to a certain depth.

        Args:
            memory_id: Center memory ID
            user_id: User ID
            depth: How many hops to traverse (default 1)

        Returns:
            Dict with "center" memory and "nodes" and "edges" lists
        """
        conn = self.get_conn()

        # Get center memory
        center = self.get_memory(memory_id, user_id)
        if not center:
            conn.close()
            return None

        visited = {memory_id}
        nodes = [center]
        edges = []

        # BFS traversal
        current_level = [memory_id]
        for _ in range(depth):
            next_level = []

            for current_id in current_level:
                # Get outgoing links
                rows = conn.execute("""
                    SELECT to_memory_id, link_type
                    FROM memory_links
                    WHERE from_memory_id = ? AND user_id = ?
                """, (current_id, user_id)).fetchall()

                for row in rows:
                    to_id = row["to_memory_id"]
                    edges.append({
                        "from": current_id,
                        "to": to_id,
                        "type": row["link_type"]
                    })

                    if to_id not in visited:
                        visited.add(to_id)
                        mem = self.get_memory(to_id, user_id)
                        if mem:
                            nodes.append(mem)
                            next_level.append(to_id)

                # Get incoming links
                rows = conn.execute("""
                    SELECT from_memory_id, link_type
                    FROM memory_links
                    WHERE to_memory_id = ? AND user_id = ?
                """, (current_id, user_id)).fetchall()

                for row in rows:
                    from_id = row["from_memory_id"]
                    edges.append({
                        "from": from_id,
                        "to": current_id,
                        "type": row["link_type"]
                    })

                    if from_id not in visited:
                        visited.add(from_id)
                        mem = self.get_memory(from_id, user_id)
                        if mem:
                            nodes.append(mem)
                            next_level.append(from_id)

            current_level = next_level

        conn.close()

        return {
            "center": center,
            "nodes": nodes,
            "edges": edges,
            "depth": depth
        }
