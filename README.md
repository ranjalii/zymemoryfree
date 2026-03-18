# Simple Memory API - Free Self-Hosted Version

A lightweight, self-hosted memory API with semantic search capabilities. No cloud dependencies, no API keys required (except optional Llama).

## Features

- **Simple Text Memories**: Store and retrieve text-based memories
- **Semantic Search**: Vector embeddings + keyword search for accurate retrieval
- **Graph Memory**: Link memories together to form a knowledge graph
- **Content Encryption**: AES-128 encryption for memory content at rest
- **API Key Authentication**: Simple, secure API key system
- **Optional AI Enhancement**: Use local Llama 8B for summaries and keyword extraction
- **SQLite Storage**: Lightweight, file-based database
- **No External Dependencies**: Runs completely offline (except Ollama if used)
- **Docker Support**: One-command deployment

## Architecture

```
┌─────────────────┐
│   Your App      │
│  (Web/Mobile)   │
└────────┬────────┘
         │ HTTP + API Key
         ▼
┌─────────────────┐
│  Memory API     │ ← FastAPI
│  (Port 8000)    │
└────────┬────────┘
         │
         ├──► SQLite DB (memories, embeddings)
         │
         └──► Ollama (optional, for AI features)
              (Port 11434)
```

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone or download this folder
cd conv_backend_free

# Start everything (API + Ollama)
docker-compose up -d

# Pull Llama model (optional, for AI features)
docker exec -it conv_backend_free-ollama-1 ollama pull llama3.1:8b-instruct-fp16

# Create API key
curl -X POST http://localhost:8000/api-keys \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user@example.com"}'

# Save the returned API key!
```

### Option 2: Local Python Setup

```bash
# Run setup script
./setup_local.sh

# Activate virtual environment
source venv/bin/activate

# Start server
python3 app_local.py
```

## API Usage

### 1. Create API Key

```bash
curl -X POST http://localhost:8000/api-keys \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user@example.com"}'
```

Response:
```json
{
  "api_key": "mem_xxxxxxxxxxxxxxxxxxxx",
  "user_id": "user@example.com",
  "message": "Save this API key securely..."
}
```

**Save this API key!** You'll need it for all subsequent requests.

### 2. Create a Memory

```bash
curl -X POST http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx" \
  -d '{
    "content": "I prefer Python for data science projects",
    "metadata": {"category": "preferences"},
    "enhance": true
  }'
```

Response:
```json
{
  "id": 1,
  "content": "I prefer Python for data science projects",
  "metadata": {
    "category": "preferences",
    "keywords": ["Python", "data science", "projects"]
  },
  "created_at": 1234567890,
  "updated_at": 1234567890
}
```

### 3. Search Memories

```bash
curl -X POST http://localhost:8000/memories/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx" \
  -d '{
    "query": "What programming language do I like?",
    "top_k": 5
  }'
```

Response:
```json
[
  {
    "id": 1,
    "content": "I prefer Python for data science projects",
    "metadata": {"category": "preferences", "keywords": ["Python", "data science"]},
    "created_at": 1234567890,
    "updated_at": 1234567890,
    "score": 0.87
  }
]
```

### 4. List All Memories

```bash
curl http://localhost:8000/memories?limit=20&offset=0 \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx"
```

### 5. Get Specific Memory

```bash
curl http://localhost:8000/memories/1 \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx"
```

### 6. Delete Memory

```bash
curl -X DELETE http://localhost:8000/memories/1 \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx"
```

### 7. Create Memory Link (Graph)

```bash
curl -X POST http://localhost:8000/graph/links \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx" \
  -d '{
    "from_memory_id": 1,
    "to_memory_id": 2,
    "link_type": "related"
  }'
```

### 8. Get Linked Memories

```bash
curl http://localhost:8000/graph/links/1?direction=both \
  -H "X-API-Key: mem_xxxxxxxxxxxxxxxxxxxx"
```

Response:
```json
{
  "memory_id": 1,
  "outgoing": [
    {
      "id": 2,
      "content": "Related memory content",
      "link_type": "related",
      "link_created_at": 1234567890
    }
  ],
  "incoming": []
}
```

### 9. Get Memory Graph

```bash
curl http://localhost:8000/graph/1?depth=2 \
  -H "X-API-Key": mem_xxxxxxxxxxxxxxxxxxxx"
```

Response:
```json
{
  "center": {"id": 1, "content": "...", ...},
  "nodes": [
    {"id": 1, ...},
    {"id": 2, ...},
    {"id": 3, ...}
  ],
  "edges": [
    {"from": 1, "to": 2, "type": "related"},
    {"from": 2, "to": 3, "type": "caused_by"}
  ],
  "depth": 2
}
```

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/` | API info | No |
| GET | `/health` | Health check | No |
| GET | `/docs` | Interactive API docs | No |
| POST | `/api-keys` | Create API key | No |
| POST | `/memories` | Create memory | Yes |
| GET | `/memories` | List memories | Yes |
| GET | `/memories/{id}` | Get memory | Yes |
| DELETE | `/memories/{id}` | Delete memory | Yes |
| POST | `/memories/search` | Search memories | Yes |
| GET | `/stats` | User statistics | Yes |

### Graph Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/graph/links` | Create link between memories | Yes |
| GET | `/graph/links/{id}` | Get linked memories | Yes |
| DELETE | `/graph/links?from_memory_id=X&to_memory_id=Y` | Delete link | Yes |
| GET | `/graph/{id}?depth=N` | Get memory graph (N hops) | Yes |

## Graph Memory

The graph memory feature allows you to create semantic links between memories, building a knowledge graph over time.

### Use Cases

1. **Causal Chains**: Link cause-and-effect memories
   ```
   "Car won't start" --causes--> "Called mechanic" --leads-to--> "Battery replaced"
   ```

2. **Related Concepts**: Group related information
   ```
   "Python basics" --related--> "List comprehensions" --related--> "Generator expressions"
   ```

3. **Timeline/Story**: Build narrative connections
   ```
   "Met Sarah at conference" --then--> "Coffee meeting" --then--> "Collaboration proposal"
   ```

4. **Dependencies**: Track prerequisite knowledge
   ```
   "Linear algebra" --required-for--> "Machine learning" --required-for--> "Neural networks"
   ```

### Link Types

Suggested link types (you can use any string):
- `related` - General relationship
- `caused_by` - Causal relationship
- `leads_to` - Temporal sequence
- `part_of` - Hierarchical relationship
- `contradicts` - Conflicting information
- `supports` - Supporting evidence
- `required_for` - Dependency

### Graph Visualization

The `/graph/{id}?depth=N` endpoint returns a graph structure that can be visualized using libraries like:
- **D3.js** (JavaScript) - Force-directed graphs
- **Cytoscape.js** (JavaScript) - Network visualizations
- **NetworkX** (Python) - Graph analysis and visualization
- **vis.js** (JavaScript) - Interactive network graphs

## Optional: Llama AI Features

The API can optionally use local Llama 8B Instruct for:
- Summarizing long text
- Extracting keywords
- Generating tags

### Setup Ollama (Optional)

```bash
# Install Ollama
# Visit: https://ollama.com/download

# Pull Llama model
ollama pull llama3.1:8b-instruct-fp16

# Start Ollama (if not already running)
ollama serve
```

### Using AI Enhancement

When creating a memory, set `"enhance": true`:

```json
{
  "content": "Long text about machine learning and neural networks...",
  "enhance": true
}
```

The API will automatically add `summary` and `keywords` to the metadata.

## Configuration

### Environment Variables

Create a `.env` file (auto-generated by `setup_local.sh`):

```bash
# Database path
DB_PATH=db/memories.db

# Encryption key (CRITICAL - KEEP SECRET!)
ENCRYPTION_KEY=<auto-generated-key>

# Ollama settings (optional)
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3.1:8b-instruct-fp16
```

### Encryption

**Content encryption is enabled by default** to protect your memories at rest.

#### How It Works

- **Algorithm**: Fernet (AES-128-CBC + HMAC-SHA256)
- **What's encrypted**: Memory content and metadata
- **What's NOT encrypted**: Embeddings (needed for fast search), user IDs, timestamps
- **Performance**: Minimal overhead (~1ms per memory)

#### Generating a New Key

```bash
# Generate and print a new encryption key
python3 encryption.py

# Output:
# ENCRYPTION_KEY=<base64-key>
```

#### Key Management

⚠️ **CRITICAL**: Backup your `.env` file!

- **Lost key = Lost data**: Encrypted memories cannot be recovered without the key
- **Store securely**: Use a password manager, encrypted backup, or secrets manager
- **Rotation**: Not supported yet - all data must be re-encrypted if key changes

#### Disabling Encryption

If you don't need encryption (not recommended):

```bash
# In .env file
ENCRYPTION_KEY=
```

**Warning**: Existing encrypted data will become inaccessible. Only disable on a fresh install.

#### Migrating Existing Data

If you have unencrypted data and want to enable encryption:

1. Backup your database: `cp db/memories.db db/memories.db.backup`
2. Generate new key: `python3 encryption.py`
3. Add key to `.env`
4. Restart server

New memories will be encrypted. Old memories remain in plaintext (the system handles both).

## Python SDK Example

```python
import requests

class MemoryClient:
    def __init__(self, api_key, base_url="http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def create(self, content, metadata=None, enhance=False):
        return requests.post(
            f"{self.base_url}/memories",
            json={"content": content, "metadata": metadata, "enhance": enhance},
            headers=self.headers
        ).json()

    def search(self, query, top_k=5):
        return requests.post(
            f"{self.base_url}/memories/search",
            json={"query": query, "top_k": top_k},
            headers=self.headers
        ).json()

    def list(self, limit=20, offset=0):
        return requests.get(
            f"{self.base_url}/memories?limit={limit}&offset={offset}",
            headers=self.headers
        ).json()

    def delete(self, memory_id):
        return requests.delete(
            f"{self.base_url}/memories/{memory_id}",
            headers=self.headers
        ).json()

# Usage
client = MemoryClient("mem_xxxxxxxxxxxxxxxxxxxx")

# Create memory
client.create("I love Python programming", {"category": "preferences"})

# Search
results = client.search("What do I love?")
print(results)
```

## Performance

- **Storage**: ~1KB per memory (text + embedding)
- **Search Speed**: <100ms for 10,000 memories on consumer hardware
- **Embedding**: ~50ms per memory (BGE-small-en-v1.5)
- **AI Enhancement**: ~2-5s with Llama 8B (optional)

## Security

### Implemented
- ✅ **Content encryption** at rest (Fernet/AES-128)
- ✅ **API key authentication** for all protected endpoints
- ✅ **User isolation** (users can only access their own memories)
- ✅ **SQLite with file permissions** (database file protection)

### Recommended for Production
- 🔒 **HTTPS**: Run behind reverse proxy (nginx/Caddy)
- 🔒 **Restrict CORS**: Limit allowed origins in production
- 🔒 **Rate limiting**: Add rate limiting middleware
- 🔒 **API key rotation**: Implement key expiration and rotation
- 🔒 **Secrets management**: Use vault or secrets manager for keys
- 🔒 **Regular backups**: Automated database and key backups

### What's NOT Protected
- ⚠️ Embeddings are stored in plaintext (needed for fast search)
- ⚠️ API keys stored as plaintext in DB (hash them for production)
- ⚠️ No protection against SQL injection (using parameterized queries is sufficient)

## Deployment

### Production Recommendations

1. **Reverse Proxy**: Use nginx or Caddy for HTTPS
2. **API Key Protection**: Restrict `/api-keys` endpoint
3. **Rate Limiting**: Add rate limiting middleware
4. **Backups**: Regularly backup `db/memories.db`
5. **CORS**: Restrict origins in production

### Example nginx config

```nginx
server {
    listen 443 ssl;
    server_name memory.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### "Llama not available"

1. Install Ollama: https://ollama.com/download
2. Pull model: `ollama pull llama3.1:8b-instruct-fp16`
3. Check Ollama is running: `curl http://localhost:11434/api/tags`

### "Invalid API key"

1. Create a new API key: `POST /api-keys`
2. Use it in `X-API-Key` header (not `Authorization`)

### Docker issues

```bash
# Check logs
docker-compose logs -f

# Restart services
docker-compose restart

# Rebuild
docker-compose down && docker-compose up --build -d
```

## Comparison with Full Version

| Feature | Free Version | Full Version |
|---------|--------------|--------------|
| Authentication | API Keys | Google OAuth + Multi-tenant |
| Storage | SQLite | PostgreSQL + Vector Extension |
| AI Model | Local Llama (optional) | Gemini API |
| Memory Structure | Simple text | Proprietary rung system |
| Encryption | Fernet (AES-128) | Multi-layer encryption |
| Repr Versioning | No | Full version history |
| Graph | Basic directed graph | Advanced rung linking |
| Access Control | User-level | Role-based (read/write/owner) |
| Scaling | Single instance | Horizontal scaling |

## License

This is the free, open-source version. Use it for personal projects, learning, or as a starting point for your own memory system.

## Support

- Documentation: `/docs` endpoint 
- Issues: Open an issue in the repository
- Community: [Your community link]

## What's Next?

- Add batch import/export
- Web UI for memory management
- Support for images and files
- Integration examples (Python, JavaScript, etc.)
- Multi-language support

---

Made with ❤️ for the open-source community
