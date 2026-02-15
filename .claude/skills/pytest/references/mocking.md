# Mocking Reference

## Contents
- Mock Objects
- Patching Strategies
- Response Mocking
- Side Effects
- Verifying Calls

## Mock Objects

Use `unittest.mock.Mock` for creating test doubles.

```python
from unittest.mock import Mock, patch, MagicMock

@pytest.fixture
def mock_torrent():
    """Create a mock torrent object with attributes"""
    torrent = Mock()
    torrent.hash = "abc123def456"
    torrent.name = "Test Book [EPUB].epub"
    torrent.state = "downloading"
    torrent.progress = 0.5
    torrent.dlspeed = 1048576
    torrent.eta = 120
    torrent.save_path = "/downloads/books"
    return torrent
```

## Patching Strategies

### Patch at Import Location

Patch where the module is imported, not where it's defined:

```python
# app/downloads/clients/qbittorrent.py imports QBClient
# Patch it there, not in qbittorrentapi module

@pytest.fixture
def mock_qb_client():
    with patch('app.downloads.clients.qbittorrent.QBClient') as mock_class:
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_instance.app.version = "v4.6.0"
        
        client = QBittorrentClient(host="localhost", port=8080, ...)
        yield client
```

### Patch Object Methods

```python
def test_successful_connection(self, mock_client):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"version": "1.0.0"}

    with patch.object(mock_client.session, 'get', return_value=mock_response):
        result = mock_client.test_connection()

    assert result is True
```

### Patch Environment Variables

```python
def test_init_with_env_vars(self):
    with patch.dict('os.environ', {
        'PROWLARR_URL': 'http://prowlarr-env:9696',
        'PROWLARR_API_KEY': 'env_key'
    }):
        source = ProwlarrSource()
        assert source.client.base_url == 'http://prowlarr-env:9696'
```

## Response Mocking

### HTTP Response Mock

```python
def test_rpc_call_success(self, mock_nzbget_client):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "test_result", "id": 1}
    mock_nzbget_client.session.post.return_value = mock_response

    result = mock_nzbget_client._rpc_call("test_method", ["param1"])

    assert result == "test_result"
```

### Chained Method Mocking

```python
# Mock response.raise_for_status() to raise
mock_response = Mock()
mock_response.raise_for_status.side_effect = requests.HTTPError("404")
```

## Side Effects

### Sequential Returns

```python
def test_retry_on_empty_results(self, mock_prowlarr_source):
    mock_prowlarr_source.client.search_with_retry.side_effect = [
        [],  # First call returns empty
        [{"title": "Book", ...}]  # Second call returns results
    ]

    results = mock_prowlarr_source.search("query", ...)
    
    assert mock_prowlarr_source.client.search_with_retry.call_count == 2
    assert len(results) == 1
```

### Exception Side Effects

```python
def test_connection_error_handling(self, mock_client):
    with patch.object(
        mock_client.session,
        'get',
        side_effect=requests.exceptions.ConnectionError()
    ):
        result = mock_client.test_connection()

    assert result is False
```

### Callable Side Effects

```python
def test_dynamic_response(self, mock_client):
    def dynamic_response(*args, **kwargs):
        if "search" in kwargs.get("params", {}).get("query", ""):
            return Mock(json=lambda: [{"title": "Found"}])
        return Mock(json=lambda: [])

    mock_client.session.get.side_effect = dynamic_response
```

## Verifying Calls

### Call Arguments

```python
def test_search_params(self, mock_client):
    with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
        mock_client.search("query", categories=[7000])

    # Positional/keyword args
    call_args = mock_get.call_args
    assert call_args.kwargs["params"]["categories"] == "7000"
```

### Call Count

```python
def test_no_retry_if_results_found(self, mock_client):
    with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
        mock_client.search_with_retry("query", categories=[7000])

    assert mock_get.call_count == 1
```

### Any Call Verification

```python
def test_progress_callbacks(self):
    progress_mock = Mock()
    
    handler.download(task, cancel_flag, progress_mock, status_mock)
    
    progress_mock.assert_any_call(0.0)
    progress_mock.assert_any_call(50.0)
    progress_mock.assert_any_call(100.0)
```

## WARNING: Mock Spec

Use `spec=` to catch typos in attribute access:

```python
# BAD - Typo silently succeeds
mock = Mock()
mock.sesion.get()  # 'sesion' typo creates new mock

# GOOD - Spec catches typos
mock = Mock(spec=ProwlarrClient)
mock.sesion.get()  # AttributeError: Mock object has no attribute 'sesion'
```