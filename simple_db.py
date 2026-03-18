"""simple_db.py - Simple SQLite memory database

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

            -- Entities extracted from memories (Knowledge Graph)
            CREATE TABLE IF NOT EXISTS entities (
                entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                entity_text TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                embedding BLOB,
                mention_count INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, entity_text, entity_type)
            );
            CREATE INDEX IF NOT EXISTS idx_entities_user ON entities(user_id);
            CREATE INDEX IF NOT EXISTS idx_entities_text ON entities(entity_text);
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);

            -- Entity mentions in specific memories
            CREATE TABLE IF NOT EXISTS entity_mentions (
                mention_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                memory_id INTEGER NOT NULL,
                mention_text TEXT NOT NULL,
                position INTEGER,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
                FOREIGN KEY (memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
            CREATE INDEX IF NOT EXISTS idx_mentions_memory ON entity_mentions(memory_id);

            -- Relationships between entities (semantic graph)
            CREATE TABLE IF NOT EXISTS entity_relationships (
                rel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_entity_id INTEGER NOT NULL,
                to_entity_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (from_entity_id) REFERENCES entities(entity_id),
                FOREIGN KEY (to_entity_id) REFERENCES entities(entity_id),
                UNIQUE(from_entity_id, to_entity_id, relationship_type)
            );
            CREATE INDEX IF NOT EXISTS idx_rel_from ON entity_relationships(from_entity_id);
            CREATE INDEX IF NOT EXISTS idx_rel_to ON entity_relationships(to_entity_id);
            CREATE INDEX IF NOT EXISTS idx_rel_user ON entity_relationships(user_id);
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

        # Extract and store entities from the new memory
        try:
            self.process_memory_entities(memory_id, user_id, content)
        except Exception as e:
            # Don't fail memory creation if entity extraction fails
            print(f"Entity extraction failed: {e}")

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

    # ---- Knowledge Graph Operations ----

    def extract_entities(self, text: str) -> List[Dict]:
        """
        Extract entities from text using simple heuristics.
        Returns list of {text, type, position} dicts.
        """
        import re
        entities = []

        # Capitalized words/phrases (potential proper nouns - people, places, orgs)
        # Match 2-4 consecutive capitalized words
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b'
        matches = re.finditer(pattern, text)
        for match in matches:
            entity_text = match.group(1)
            # Skip common words that start sentences
            if entity_text.lower() not in {'the', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}:
                entities.append({
                    'text': entity_text,
                    'type': 'ENTITY',  # Generic type, can be enhanced with NER
                    'position': match.start()
                })

        # Email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, text):
            entities.append({
                'text': match.group(0),
                'type': 'EMAIL',
                'position': match.start()
            })

        # URLs
        url_pattern = r'https?://[^\s]+'
        for match in re.finditer(url_pattern, text):
            entities.append({
                'text': match.group(0),
                'type': 'URL',
                'position': match.start()
            })

        # Phone numbers (simple pattern)
        phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        for match in re.finditer(phone_pattern, text):
            entities.append({
                'text': match.group(0),
                'type': 'PHONE',
                'position': match.start()
            })

        # Dates (simple patterns)
        date_pattern = r'\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b'
        for match in re.finditer(date_pattern, text):
            entities.append({
                'text': match.group(0),
                'type': 'DATE',
                'position': match.start()
            })

        return entities

    def create_or_update_entity(self, user_id: str, entity_text: str, entity_type: str) -> int:
        """Create or update an entity, return entity_id."""
        conn = self.get_conn()
        cursor = conn.cursor()
        now = int(time.time())

        # Normalize entity text
        entity_text_norm = entity_text.strip()

        # Try to get existing entity
        row = cursor.execute(
            "SELECT entity_id, mention_count FROM entities WHERE user_id = ? AND entity_text = ? AND entity_type = ?",
            (user_id, entity_text_norm, entity_type)
        ).fetchone()

        if row:
            # Update mention count
            entity_id = row['entity_id']
            cursor.execute(
                "UPDATE entities SET mention_count = ?, updated_at = ? WHERE entity_id = ?",
                (row['mention_count'] + 1, now, entity_id)
            )
        else:
            # Create new entity with embedding
            embedding = np.array(next(embedder.embed([entity_text_norm])), dtype=np.float32)
            cursor.execute(
                "INSERT INTO entities (user_id, entity_text, entity_type, embedding, mention_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (user_id, entity_text_norm, entity_type, embedding.tobytes(), now, now)
            )
            entity_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return entity_id

    def create_entity_mention(self, entity_id: int, memory_id: int, mention_text: str, position: int):
        """Record an entity mention in a specific memory."""
        conn = self.get_conn()
        conn.execute(
            "INSERT INTO entity_mentions (entity_id, memory_id, mention_text, position, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (entity_id, memory_id, mention_text, position, int(time.time()))
        )
        conn.commit()
        conn.close()

    def infer_entity_relationships(self, memory_id: int, user_id: str, entity_ids: List[int]):
        """
        Infer relationships between entities that appear in the same memory.
        Creates CO_OCCURS relationships with confidence based on frequency.
        """
        if len(entity_ids) < 2:
            return

        conn = self.get_conn()
        cursor = conn.cursor()
        now = int(time.time())

        # Create relationships between all pairs of entities
        for i, from_id in enumerate(entity_ids):
            for to_id in entity_ids[i+1:]:
                # Try to update existing relationship
                row = cursor.execute(
                    "SELECT rel_id, evidence_count, confidence FROM entity_relationships "
                    "WHERE from_entity_id = ? AND to_entity_id = ? AND relationship_type = ?",
                    (from_id, to_id, 'CO_OCCURS')
                ).fetchone()

                if row:
                    # Increase evidence and confidence
                    new_count = row['evidence_count'] + 1
                    new_confidence = min(0.95, row['confidence'] + 0.1)
                    cursor.execute(
                        "UPDATE entity_relationships SET evidence_count = ?, confidence = ?, updated_at = ? WHERE rel_id = ?",
                        (new_count, new_confidence, now, row['rel_id'])
                    )
                else:
                    # Create new relationship
                    cursor.execute(
                        "INSERT INTO entity_relationships "
                        "(from_entity_id, to_entity_id, user_id, relationship_type, confidence, evidence_count, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                        (from_id, to_id, user_id, 'CO_OCCURS', 0.5, now, now)
                    )

        conn.commit()
        conn.close()

    def process_memory_entities(self, memory_id: int, user_id: str, content: str):
        """Extract and store entities from a memory."""
        entities = self.extract_entities(content)
        entity_ids = []

        for entity_data in entities:
            entity_id = self.create_or_update_entity(
                user_id,
                entity_data['text'],
                entity_data['type']
            )
            entity_ids.append(entity_id)

            self.create_entity_mention(
                entity_id,
                memory_id,
                entity_data['text'],
                entity_data.get('position', 0)
            )

        # Infer relationships between entities
        if entity_ids:
            self.infer_entity_relationships(memory_id, user_id, entity_ids)

    def get_memory_entities(self, memory_id: int, user_id: str) -> List[Dict]:
        """Get all entities mentioned in a memory."""
        conn = self.get_conn()
        rows = conn.execute("""
            SELECT e.entity_id, e.entity_text, e.entity_type, em.mention_text, em.position
            FROM entity_mentions em
            JOIN entities e ON e.entity_id = em.entity_id
            WHERE em.memory_id = ? AND e.user_id = ?
            ORDER BY em.position
        """, (memory_id, user_id)).fetchall()
        conn.close()

        return [{
            'entity_id': row['entity_id'],
            'entity_text': row['entity_text'],
            'entity_type': row['entity_type'],
            'mention_text': row['mention_text'],
            'position': row['position']
        } for row in rows]

    def get_entity_graph(self, entity_id: int, user_id: str, depth: int = 1) -> Dict:
        """Get related entities up to a certain depth."""
        conn = self.get_conn()

        # Get center entity
        center = conn.execute(
            "SELECT entity_id, entity_text, entity_type, mention_count FROM entities WHERE entity_id = ? AND user_id = ?",
            (entity_id, user_id)
        ).fetchone()

        if not center:
            conn.close()
            return None

        visited = {entity_id}
        nodes = [dict(center)]
        edges = []

        # BFS traversal through entity relationships
        current_level = [entity_id]
        for _ in range(depth):
            next_level = []

            for current_id in current_level:
                # Get outgoing relationships
                rows = conn.execute("""
                    SELECT to_entity_id, relationship_type, confidence, evidence_count
                    FROM entity_relationships
                    WHERE from_entity_id = ? AND user_id = ?
                """, (current_id, user_id)).fetchall()

                for row in rows:
                    to_id = row['to_entity_id']
                    edges.append({
                        'from': current_id,
                        'to': to_id,
                        'type': row['relationship_type'],
                        'confidence': row['confidence'],
                        'evidence_count': row['evidence_count']
                    })

                    if to_id not in visited:
                        visited.add(to_id)
                        entity = conn.execute(
                            "SELECT entity_id, entity_text, entity_type, mention_count FROM entities WHERE entity_id = ?",
                            (to_id,)
                        ).fetchone()
                        if entity:
                            nodes.append(dict(entity))
                            next_level.append(to_id)

            current_level = next_level

        conn.close()
        return {
            'center': dict(center),
            'nodes': nodes,
            'edges': edges,
            'depth': depth
        }

    def search_by_entities(self, user_id: str, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search memories by finding relevant entities first, then retrieving memories
        containing those entities (entity-centric retrieval).
        """
        # Extract entities from query
        query_entities = self.extract_entities(query)

        if not query_entities:
            # Fall back to regular search if no entities found
            return self.search_memories(user_id, query, top_k)

        conn = self.get_conn()

        # Find matching entities in DB
        entity_matches = []
        for qe in query_entities:
            rows = conn.execute(
                "SELECT entity_id, entity_text, entity_type FROM entities "
                "WHERE user_id = ? AND (entity_text LIKE ? OR entity_text = ?)",
                (user_id, f"%{qe['text']}%", qe['text'])
            ).fetchall()
            entity_matches.extend([row['entity_id'] for row in rows])

        if not entity_matches:
            conn.close()
            return self.search_memories(user_id, query, top_k)

        # Get memories containing these entities
        memory_scores = {}
        for entity_id in entity_matches:
            rows = conn.execute(
                "SELECT DISTINCT memory_id FROM entity_mentions WHERE entity_id = ?",
                (entity_id,)
            ).fetchall()

            for row in rows:
                mid = row['memory_id']
                memory_scores[mid] = memory_scores.get(mid, 0) + 1  # Score by entity count

        # Retrieve and decrypt memories
        results = []
        for memory_id, entity_count in sorted(memory_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]:
            mem = self.get_memory(memory_id, user_id)
            if mem:
                mem['score'] = float(entity_count) / len(entity_matches)  # Normalize score
                mem['matched_entities'] = entity_count
                results.append(mem)

        conn.close()
        return results

    def graph_enhanced_search(self, user_id: str, query: str, top_k: int = 5) -> List[Dict]:
        """
        Hybrid search combining vector similarity, entity matching, and graph expansion.
        Best of all worlds for Knowledge Graph RAG.
        """
        # 1. Get vector search results
        vector_results = self.search_memories(user_id, query, top_k * 2)
        vector_ids = {r['id']: r['score'] for r in vector_results}

        # 2. Get entity-based results
        entity_results = self.search_by_entities(user_id, query, top_k * 2)
        entity_ids = {r['id']: r.get('score', 0.5) for r in entity_results}

        # 3. Combine scores
        all_memory_ids = set(vector_ids.keys()) | set(entity_ids.keys())
        combined_results = []

        for mem_id in all_memory_ids:
            mem = self.get_memory(mem_id, user_id)
            if mem:
                # Combined score: 60% vector, 40% entity
                vec_score = vector_ids.get(mem_id, 0)
                ent_score = entity_ids.get(mem_id, 0)
                combined_score = (vec_score * 0.6) + (ent_score * 0.4)

                mem['score'] = combined_score
                mem['vector_score'] = vec_score
                mem['entity_score'] = ent_score
                combined_results.append(mem)

        # Sort by combined score
        combined_results.sort(key=lambda x: x['score'], reverse=True)
        return combined_results[:top_k]

    def get_all_entities(self, user_id: str, limit: int = 100) -> List[Dict]:
        """Get all entities for a user."""
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT entity_id, entity_text, entity_type, mention_count, created_at "
            "FROM entities WHERE user_id = ? ORDER BY mention_count DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_entity_memories(self, entity_id: int, user_id: str) -> List[Dict]:
        """Get all memories containing a specific entity."""
        conn = self.get_conn()
        rows = conn.execute("""
            SELECT DISTINCT m.memory_id
            FROM entity_mentions em
            JOIN memories m ON m.memory_id = em.memory_id
            WHERE em.entity_id = ? AND m.user_id = ?
        """, (entity_id, user_id)).fetchall()
        conn.close()

        return [self.get_memory(row['memory_id'], user_id) for row in rows]
