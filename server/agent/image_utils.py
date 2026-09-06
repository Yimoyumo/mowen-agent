"""图片处理工具：压缩为 token 友好的 data URL，供多模态消息注入。

将图片缩小到 max_size px（最长边）并转 JPEG 压缩，再编码为
`data:image/jpeg;base64,...` 形式，可直接作为 LangChain 消息的
image_url content block 使用。

两处调用共用同一套流程：
- graph.py：用户在对话中上传的图片 → 注入 HumanMessage
- tools.py read_file：Agent 读取工作区图片 → 注入 ToolMessage

典型效果：2MB PNG → 80KB JPEG → ~20K tokens。
"""

import base64
import io
from pathlib import Path

from server.core.logging_config import get_logger

logger = get_logger(__name__)


def compress_image_to_data_url(
    source: "str | Path | bytes", max_size: int = 1024, quality: int = 75
) -> str | None:
    """压缩图片并返回 base64 data URL。

    Args:
        source: 图片文件路径（宿主机路径）或原始字节内容
        max_size: 最长边像素上限，超出则等比缩小
        quality: JPEG 压缩质量

    Returns:
        `data:image/jpeg;base64,...` 字符串；解码 / 打开失败时返回 None
    """
    from PIL import Image

    try:
        if isinstance(source, bytes):
            img = Image.open(io.BytesIO(source))
        else:
            img = Image.open(source)
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        raw = buf.getvalue()
        logger.debug("图片压缩: %dx%d → %dx%d, %d bytes", w, h, img.width, img.height, len(raw))
        return f"data:image/jpeg;base64,{base64.b64encode(raw).decode('utf-8')}"
    except Exception as e:
        src_desc = source if isinstance(source, (str, Path)) else f"<bytes {len(source)}B>"
        logger.warning("图片压缩失败: %s (%s)", src_desc, e)
        return None
