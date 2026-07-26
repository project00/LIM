```python
                        except Exception as e:
                            logger.error(
                                f"Errore non gestito durante l'invio della trascrizione: {e}",
                                exc_info=True
                            )
```

```python
                            remote_analyze_url = f"{settings.remote_base_url}/api/v1/analyze"
```
Built from settings.remote_base_url: YES
