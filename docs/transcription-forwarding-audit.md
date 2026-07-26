# Transcription Forwarding Audit

## 1. Message construction sent to the widget
```python
                            websocket_msg = {
                                "type": "subtitle",
                                "source": "remote_stt",
                                "text": response_data.get("text"),
                                "translated_text": response_data.get("translated_text"),
                                "is_final": True
                            }

                            if self.websocket:
                                await self.websocket.send_text(json.dumps(websocket_msg))
```

Message includes is_final: true: YES
Message includes source: remote_stt: YES

## 2. Except clause(s) wrapping the POST call
```python
                        except (httpx.ConnectError, httpx.TimeoutException) as e:
                            logger.warning(
                                f"Server remoto irraggiungibile per la trascrizione audio: {e}"
                            )
                            fallback_msg = {
                                "type": "system_warning",
                                "message": "Server remoto offline. Passaggio a Modalità Locale.",
                            }
                            if self.websocket:
                                try:
                                    await self.websocket.send_text(json.dumps(fallback_msg))
                                except Exception as ws_err:
                                    logger.error(
                                        f"Failed to send system_warning to websocket: {ws_err}"
                                    )
                        except Exception as e:
                            logger.error(
                                f"Errore non gestito durante l'invio della trascrizione: {e}"
                            )
```

Exception types caught: httpx.ConnectError, httpx.TimeoutException, Exception

## 3. Header construction
```python
                        headers = {}
                        if settings.api_key:
                            headers["Authorization"] = f"Bearer {settings.api_key}"
```

## 4. POST call execution
```python
                            response = await http_client.post(
                                remote_analyze_url,
                                json=payload,
                                headers=headers
                            )
```

Call is async (await httpx.AsyncClient): YES
