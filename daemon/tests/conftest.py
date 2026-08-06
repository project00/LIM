import sys
from unittest.mock import MagicMock

# Mock piper and onnxruntime entirely at the import level
# to prevent any real onnxruntime / piper loading or initialization in tests.
sys.modules["piper"] = MagicMock()
sys.modules["onnxruntime"] = MagicMock()
