"""test_api.py - Simple test script for the Memory API

Run this after starting the server to test all endpoints.
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"
API_KEY = None


def test_health():
    """Test health endpoint."""
    print("\n1. Testing /health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    assert response.status_code == 200


def test_create_api_key():
    """Test API key creation."""
    global API_KEY
    print("\n2. Creating API key...")

    user_id = f"test-user-{int(time.time())}"
    response = requests.post(
        f"{BASE_URL}/api-keys",
        json={"user_id": user_id}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   User ID: {data['user_id']}")
    print(f"   API Key: {data['api_key'][:20]}...")

    API_KEY = data['api_key']
    assert response.status_code == 200
    return user_id


def test_create_memory():
    """Test memory creation."""
    print("\n3. Creating memory...")

    response = requests.post(
        f"{BASE_URL}/memories",
        json={
            "content": "I love Python programming and machine learning",
            "metadata": {"category": "preferences"},
            "enhance": False  # Set to True if Ollama is running
        },
        headers={"X-API-Key": API_KEY}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Memory ID: {data['id']}")
    print(f"   Content: {data['content'][:50]}...")

    assert response.status_code == 200
    return data['id']


def test_list_memories():
    """Test listing memories."""
    print("\n4. Listing memories...")

    response = requests.get(
        f"{BASE_URL}/memories?limit=10",
        headers={"X-API-Key": API_KEY}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Total memories: {len(data)}")

    assert response.status_code == 200
    return data


def test_search_memories():
    """Test memory search."""
    print("\n5. Searching memories...")

    response = requests.post(
        f"{BASE_URL}/memories/search",
        json={
            "query": "What programming language do I like?",
            "top_k": 3
        },
        headers={"X-API-Key": API_KEY}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Results found: {len(data)}")

    if data:
        print(f"   Top result: {data[0]['content'][:50]}...")
        print(f"   Score: {data[0]['score']:.3f}")

    assert response.status_code == 200


def test_get_memory(memory_id):
    """Test getting a specific memory."""
    print(f"\n6. Getting memory {memory_id}...")

    response = requests.get(
        f"{BASE_URL}/memories/{memory_id}",
        headers={"X-API-Key": API_KEY}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Content: {data['content'][:50]}...")

    assert response.status_code == 200


def test_stats():
    """Test stats endpoint."""
    print("\n7. Getting stats...")

    response = requests.get(
        f"{BASE_URL}/stats",
        headers={"X-API-Key": API_KEY}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Total memories: {data['total_memories']}")
    print(f"   Llama available: {data['llama_available']}")

    assert response.status_code == 200


def test_delete_memory(memory_id):
    """Test memory deletion."""
    print(f"\n8. Deleting memory {memory_id}...")

    response = requests.delete(
        f"{BASE_URL}/memories/{memory_id}",
        headers={"X-API-Key": API_KEY}
    )

    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Success: {data['success']}")

    assert response.status_code == 200


def main():
    """Run all tests."""
    print("=" * 60)
    print("Simple Memory API - Test Suite")
    print("=" * 60)

    try:
        test_health()
        user_id = test_create_api_key()
        memory_id = test_create_memory()
        test_list_memories()
        test_search_memories()
        test_get_memory(memory_id)
        test_stats()
        test_delete_memory(memory_id)

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        print(f"\nYour test API key: {API_KEY}")
        print("Save this key to use the API")

    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to API")
        print("Make sure the server is running: python3 app_local.py")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
