## 1. Verbatim Test Functions Covering fast_ocr Handler

```python
@pytest.mark.asyncio
async def test_fast_ocr_capture_success_with_ocr_mock() -> None:
    """Tests that fast_ocr executes local screen capture and runs tesseract successfully."""
    client = TestClient(app)

    mock_sct_img = MagicMock()
    mock_sct_img.size = (100, 100)
    mock_sct_img.bgra = b"\x00" * (100 * 100 * 4)

    with patch("local_bridge.mss") as mock_mss, \
         patch("local_bridge.Image.frombytes") as mock_frombytes, \
         patch("local_bridge.pytesseract.image_to_string") as mock_ocr:

        mock_instance = mock_mss.return_value.__enter__.return_value
        mock_instance.grab.return_value = mock_sct_img
        mock_ocr.return_value = "TEST OCR SUCCESSFUL CONTENT"

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "fast_ocr",
                "data": {"region": {"x": 10, "y": 20, "width": 100, "height": 100}}
            }))
            response = websocket.receive_json()
            assert response["type"] == "ocr"
            assert response["source"] == "local_engine"
            assert response["text"] == "TEST OCR SUCCESSFUL CONTENT"


@pytest.mark.asyncio
async def test_fast_ocr_capture_headless_failure() -> None:
    """Tests that fast_ocr correctly catches and reports display access failures under headless environments."""
    client = TestClient(app)

    with patch("local_bridge.mss") as mock_mss:
        mock_mss.side_effect = Exception("No DISPLAY environment variable found")

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "fast_ocr",
                "data": {"region": {"x": 0, "y": 0, "width": 1920, "height": 1080}}
            }))
            response = websocket.receive_json()
            assert response["type"] == "ocr"
            assert response["source"] == "local_engine"
            assert "cattura fallita" in response["text"]
            assert "No DISPLAY" in response["text"]
```

## 2. mss.grab() Execution Status in Tests

mss.grab() in this test is: MOCKED

## 3. Verbatim Mock Code Used

```python
    with patch("local_bridge.mss") as mock_mss, \
         patch("local_bridge.Image.frombytes") as mock_frombytes, \
         patch("local_bridge.pytesseract.image_to_string") as mock_ocr:

        mock_instance = mock_mss.return_value.__enter__.return_value
        mock_instance.grab.return_value = mock_sct_img
        mock_ocr.return_value = "TEST OCR SUCCESSFUL CONTENT"
```

## 4. Raw mss.grab() Connecting Exception

```
<string>:1: DeprecationWarning: mss.mss is deprecated and will be removed in a future release; use mss.MSS instead
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/factory.py", line 22, in mss
    return MSS(**kwargs)
           ^^^^^^^^^^^^^
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/base.py", line 237, in __init__
    self._impl: MSSImplementation = _choose_impl(
                                    ^^^^^^^^^^^^^
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/base.py", line 158, in _choose_impl
    return choose_impl_linux(**kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/linux/__init__.py", line 91, in choose_impl
    return MSSImplXShmGetImage(**kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/linux/xshmgetimage.py", line 49, in __init__
    super().__init__(display=display, with_cursor=with_cursor)
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/linux/base.py", line 54, in __init__
    self.conn, pref_screen_num = xcb.connect(display)
                                 ^^^^^^^^^^^^^^^^^^^^
  File "/home/jules/.pyenv/versions/3.12.13/lib/python3.12/site-packages/mss/linux/xcb.py", line 363, in connect
    raise XError(msg)
mss.linux.xcbhelpers.XError: Cannot connect to display: display is unset or invalid (check $DISPLAY)
```

## 5. Pytesseract Import Status from Daemon Environment

pytesseract import from daemon/'s poetry env: SUCCESS

```bash
$ cd daemon && poetry run python3 -c "import pytesseract; print('Pytesseract is successfully importable from daemon runtime environment specifically!')"
Pytesseract is successfully importable from daemon runtime environment specifically!
```
