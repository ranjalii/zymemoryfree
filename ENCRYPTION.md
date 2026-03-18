# Encryption Guide

## Overview

The Simple Memory API uses **Fernet** (symmetric encryption) to protect memory content at rest. This document explains how encryption works and how to manage it.

## What is Fernet?

Fernet is a symmetric encryption standard that provides:
- **AES-128-CBC**: Strong encryption algorithm
- **HMAC-SHA256**: Message authentication
- **Timestamp verification**: Built-in protection against replay attacks
- **Automatic IV generation**: Each encryption uses a unique initialization vector

## What Gets Encrypted?

### Encrypted ✅
- Memory content (the actual text)
- Metadata (additional information attached to memories)

### NOT Encrypted ❌
- **Embeddings**: Vector representations needed for semantic search
- **User IDs**: Required for query filtering
- **Timestamps**: Created/updated times
- **Memory IDs**: Primary keys
- **Link information**: Graph structure

## Why Aren't Embeddings Encrypted?

Embeddings must remain in plaintext to enable fast vector similarity search. Searching encrypted embeddings would require:
1. Decrypting every embedding
2. Computing similarity
3. Re-encrypting results

This would be prohibitively slow (~100x slower for 10K memories).

**Mitigation**: Embeddings don't directly reveal content - they're 384-dimensional vectors that are hard to reverse-engineer.

## Key Management

### Generation

```bash
# Generate a new key
python3 encryption.py

# Output:
ENCRYPTION_KEY=gAAAAABgxxxxxxxxxxxxxxxxxxxxxxxxxx...
```

### Storage

Your encryption key is stored in `.env`:

```bash
ENCRYPTION_KEY=gAAAAABgxxxxxxxxxxxxxxxxxxxxxxxxxx...
```

⚠️ **CRITICAL**: This file must be:
- Kept secret (never commit to git)
- Backed up securely
- Protected with file permissions (chmod 600 .env)

### Backup Strategy

**Option 1: Password Manager**
```bash
# Export key to password manager
cat .env | grep ENCRYPTION_KEY
```

**Option 2: Encrypted Backup**
```bash
# Encrypt the .env file itself
gpg -c .env  # Creates .env.gpg
```

**Option 3: Cloud Secrets Manager**
```bash
# AWS Secrets Manager
aws secretsmanager create-secret \
  --name memory-api-encryption-key \
  --secret-string "$(cat .env | grep ENCRYPTION_KEY)"
```

## Key Rotation

⚠️ **Not yet supported**

To rotate keys, you would need to:
1. Decrypt all memories with old key
2. Re-encrypt with new key
3. Update embeddings if needed

Currently, this must be done manually. A migration script may be added in the future.

## Performance Impact

Encryption adds minimal overhead:
- **Encrypt**: ~0.5ms per memory
- **Decrypt**: ~0.5ms per memory
- **Search**: No impact (embeddings not encrypted)
- **Bulk operations**: ~1-2% slower

## Disabling Encryption

**Not recommended**, but possible:

```bash
# In .env
ENCRYPTION_KEY=
```

**Consequences**:
- New memories stored in plaintext
- Existing encrypted memories become inaccessible
- Database file is readable by anyone with access

## Migration Scenarios

### Scenario 1: Adding Encryption to Existing System

You have unencrypted data and want to enable encryption.

**Steps**:
1. Backup database: `cp db/memories.db db/memories.db.backup`
2. Generate key: `python3 encryption.py`
3. Add key to `.env`
4. Restart server

**Result**:
- New memories: Encrypted
- Old memories: Remain plaintext (system handles both)

**To fully encrypt old data**: Export → Delete → Re-import

### Scenario 2: Recovering from Lost Key

You lost your encryption key and have encrypted data.

**Status**: ❌ **Data is unrecoverable**

Fernet encryption is designed to be unbreakable without the key. Options:
1. Restore from backup if you have `.env` backup
2. Start fresh (delete database, generate new key)

### Scenario 3: Migrating Between Instances

Move encrypted data to a new server.

**Steps**:
1. Copy `db/memories.db` to new server
2. Copy `.env` (including `ENCRYPTION_KEY`) to new server
3. Start server

**Critical**: Both files must be transferred.

## Security Best Practices

### DO ✅
- Generate a new key for each installation
- Backup your `.env` file securely
- Use HTTPS in production
- Set file permissions: `chmod 600 .env`
- Rotate API keys regularly
- Monitor access logs

### DON'T ❌
- Commit `.env` to version control
- Share encryption keys via email/chat
- Reuse keys across environments
- Store keys in plaintext on shared drives
- Disable encryption for sensitive data

## Compliance

### GDPR
- ✅ Encryption at rest helps meet security requirements
- ✅ User isolation supports data portability
- ⚠️ Need to add deletion audit trail
- ⚠️ Need to add consent management

### HIPAA
- ✅ Encryption at rest (164.312(a)(2)(iv))
- ⚠️ Need access control logs
- ⚠️ Need to add key management procedures
- ⚠️ Need transmission security (use HTTPS)

**Note**: This system alone is NOT sufficient for HIPAA/GDPR compliance. Additional controls required.

## Troubleshooting

### "Invalid encryption key" error

**Cause**: Key format is incorrect

**Fix**:
```bash
# Regenerate key
python3 encryption.py

# Copy output to .env
ENCRYPTION_KEY=<new-key>
```

### "Decryption error" when reading memories

**Cause**: Wrong key or corrupted data

**Checks**:
1. Verify key in `.env` matches original
2. Check database file isn't corrupted
3. Try backup database

### Slow performance after enabling encryption

**Unlikely**: Encryption adds <1ms overhead

**If it's slow**:
- Check disk I/O (SSD recommended)
- Check database size (vacuum if large)
- Check embedding generation (not encryption)

## Technical Details

### Algorithm Specs

```
Encryption: AES-128-CBC
MAC: HMAC-SHA256
KDF: PBKDF2 (for key derivation)
IV: Random, generated per encryption
Key Size: 32 bytes (256 bits)
```

### Implementation

```python
from cryptography.fernet import Fernet

# Key generation
key = Fernet.generate_key()  # 32 bytes, base64-encoded

# Encryption
f = Fernet(key)
ciphertext = f.encrypt(b"plaintext")

# Decryption
plaintext = f.decrypt(ciphertext)
```

### Storage Format

Encrypted fields in SQLite:

```
content: <fernet-token>
metadata: <fernet-token>
embedding: <binary-blob>  # NOT encrypted
```

Fernet token format:
```
base64(version || timestamp || iv || ciphertext || hmac)
```

## FAQ

**Q: Can embeddings leak information?**
A: Embeddings are abstract vectors. Reverse-engineering content from embeddings is extremely difficult and requires sophisticated attacks.

**Q: What if someone steals my database file?**
A: Without the encryption key, the content and metadata are unreadable. However, they could see:
- User IDs
- Memory IDs
- Timestamps
- Graph structure
- Embeddings (abstract vectors)

**Q: Should I encrypt embeddings too?**
A: Only if you're willing to sacrifice search performance. Consider using a separate secure database for highly sensitive data.

**Q: Can I use my own encryption algorithm?**
A: Yes, modify `encryption.py` to use your preferred algorithm. Ensure it's:
- Authenticated (HMAC or AEAD)
- Uses unique IVs
- Cryptographically secure

**Q: How do I export encrypted data?**
A: Export includes encrypted content. To decrypt during export:
1. Read memories via API (auto-decrypts)
2. Export JSON/CSV from API responses
3. Encrypted database exports are useless without key

---

For more information, see the [Fernet spec](https://github.com/fernet/spec/blob/master/Spec.md).
