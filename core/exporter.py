"""保存 Markdown 与图片；预习单 PDF 导出留待后续阶段实现。"""

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

from .models import ConversionResult, ImageNode


def save_markdown(result: ConversionResult, destination: str | Path, *, markdown: str | None = None) -> Path:
    """复制实际被引用的图片，再以原子替换方式保存 UTF-8 Markdown。"""
    target = Path(destination).expanduser().resolve()
    if target.suffix.lower() != ".md":
        target = target.with_suffix(".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = result.markdown if markdown is None else markdown
    images = [
        node for section in result.document.sections for node in section.content
        if isinstance(node, ImageNode)
    ]
    assets_name = target.stem + "_assets"
    for node in images:
        old_path = quote(node.path.replace("\\", "/"), safe="/-._~")
        if f"]({old_path})" not in text:
            continue
        source = (result.work_dir / node.path).resolve()
        if not source.is_relative_to(result.assets_dir.resolve()):
            raise ValueError("图片路径超出了当前转换的资源目录。")
        data = source.read_bytes()
        name = hashlib.sha256(data).hexdigest()[:20] + ".png"
        asset_target = target.parent / assets_name / name
        asset_target.parent.mkdir(parents=True, exist_ok=True)
        if not asset_target.exists():
            _atomic_write(asset_target, data)
        new_path = quote(assets_name + "/" + name, safe="/-._~")
        text = text.replace(f"]({old_path})", f"]({new_path})")
    _atomic_write(target, text.encode("utf-8"))
    return target


def _atomic_write(target: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".save-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
