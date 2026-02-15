# Unit Testing Reference

## Contents
- Test Class Organization
- Fixture Patterns
- Assertion Patterns
- Testing Error Conditions
- Common Anti-Patterns

## Test Class Organization

Group tests by functionality using classes. Each class tests one component aspect.

```python
# backend/tests/downloads/test_prowlarr_api.py

class TestProwlarrClientInit:
    """Test client initialization"""

    def test_init_with_trailing_slash(self):
        client = ProwlarrClient("http://prowlarr:9696/", "key")
        assert client.base_url == "http://prowlarr:9696"

    def test_init_sets_headers(self):
        client = ProwlarrClient("http://prowlarr:9696", "my_key")
        assert client.session.headers["X-Api-Key"] == "my_key"


class TestSearch:
    """Test search functionality"""

    def test_basic_search(self, mock_client):
        # Test implementation
        pass
```

## Fixture Patterns

### Component Fixture with Mocked Dependencies

```python
@pytest.fixture
def mock_client():
    """Create ProwlarrClient with mocked session"""
    client = ProwlarrClient(
        base_url="http://prowlarr:9696",
        api_key="test_api_key",
        timeout=30
    )
    return client
```

### Data Fixtures for Test Input

```python
@pytest.fixture
def mock_torrent():
    """Create a mock torrent object"""
    torrent = Mock()
    torrent.hash = "abc123def456"
    torrent.name = "Test Book [EPUB].epub"
    torrent.state = "downloading"
    torrent.progress = 0.5
    torrent.dlspeed = 1048576
    return torrent


@pytest.fixture
def sample_torrent_bytes():
    """Create valid torrent file bytes for testing"""
    info_dict = {
        'name': 'Test Book.epub',
        'piece length': 262144,
        'pieces': b'\x00' * 20,
        'length': 1024000,
    }
    torrent_dict = {'announce': 'http://tracker.example.com', 'info': info_dict}
    return _bencode(torrent_dict)
```

## Assertion Patterns

### Boolean Results

```python
def test_successful_connection(self, mock_client):
    result = mock_client.test_connection()
    assert result is True  # Use 'is' for booleans

def test_failed_connection(self, mock_client):
    with patch.object(mock_client.session, 'get', side_effect=Exception()):
        result = mock_client.test_connection()
    assert result is False
```

### Collection Results

```python
def test_get_indexers_success(self, mock_client):
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": 1, "name": "Indexer1"},
        {"id": 2, "name": "Indexer2"},
    ]
    
    with patch.object(mock_client.session, 'get', return_value=mock_response):
        indexers = mock_client.get_indexers()

    assert len(indexers) == 2
    assert indexers[0]["name"] == "Indexer1"
```

### Verifying Call Arguments

```python
def test_search_with_categories(self, mock_client):
    with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
        mock_client.search("query", categories=[7000, 7020])

    call_kwargs = mock_get.call_args.kwargs
    assert "params" in call_kwargs
    assert call_kwargs["params"]["categories"] == "7000,7020"
```

## Testing Error Conditions

### Expected Exceptions

```python
def test_add_torrent_no_source_provided(self, mock_qb_client):
    with pytest.raises(ValueError, match="Must provide url, magnet, or torrent_file"):
        mock_qb_client.add_torrent()
```

### Graceful Error Handling

```python
def test_search_timeout(self, mock_client):
    with patch.object(
        mock_client.session,
        'get',
        side_effect=requests.exceptions.Timeout()
    ):
        results = mock_client.search("query")

    assert results == []  # Returns empty, doesn't raise
```

## WARNING: Common Anti-Patterns

### Testing Implementation Instead of Behavior

```python
# BAD - Tests internal state
def test_bad_internal_check(self, client):
    client.search("query")
    assert client._internal_cache == {"query": [...]}

# GOOD - Tests observable behavior
def test_good_behavior_check(self, client):
    results = client.search("query")
    assert len(results) == 2
```

### Over-Mocking

```python
# BAD - Mocking the thing you're testing
def test_bad_over_mock(self):
    client = Mock()
    client.search.return_value = []
    assert client.search("q") == []  # Tests nothing

# GOOD - Mock dependencies, test real code
def test_good_mock_deps(self):
    with patch.object(client.session, 'get', return_value=mock_response):
        results = client.search("q")
    assert results == expected
```