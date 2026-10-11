"""测试路径：使 `pytest tests` 无须 PYTHONPATH 也能导入 thuai10。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
