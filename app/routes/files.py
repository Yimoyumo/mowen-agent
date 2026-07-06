"""文件上传与下载路由。

上传: POST /api/upload → 文件暂存到 uploads/
下载: GET  /api/download/{token}/{filename} → 从 downloads/ 提供沙盒导出的文件
"""

import mimetypes
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse

from app.errors import ForbiddenError, NotFoundError, ValidationError
from server.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

_DOWNLOADS_DIR = Path("downloads")
_UPLOADS_DIR = Path("uploads")
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 上传文件大小限制：50MB
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# 允许上传的文件扩展名（白名单）
_ALLOWED_EXTS = {
    # 文档
    '.txt', '.md', '.json', '.csv', '.pdf', '.docx', '.xlsx',
    # 代码
    '.py', '.js', '.ts', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.sh', '.sql',
    '.yaml', '.yml', '.toml', '.ini', '.xml', '.html', '.css',
    # 图片
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp',
    # 压缩包
    '.zip', '.tar', '.gz', '.tgz', '.bz2', '.7z',
}

# 图片扩展名 → 浏览器内联显示（而非下载）
_INLINE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.txt', '.csv', '.json', '.md'}


def _sanitize_filename(filename: str | None) -> str:
    """清理文件名：只保留文件名部分，去除路径穿越字符。"""
    if not filename:
        return "unnamed"
    # 只取文件名部分（去除任何路径前缀）
    safe_name = Path(filename).name
    if not safe_name or safe_name in (".", ".."):
        return "unnamed"
    return safe_name


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """上传文件到暂存区，返回 file token 供 Agent 使用。

    前端上传文件后，将返回的 token + filename 加入 ChatRequest.uploaded_files，
    Agent 会自动将文件导入沙盒处理。

    限制：最大 50MB，仅允许文档/代码/图片/压缩包类型。
    """
    safe_filename = _sanitize_filename(file.filename)

    # 校验文件类型（白名单）
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in _ALLOWED_EXTS:
        raise ValidationError(
            f"不支持的文件类型: {suffix or '无扩展名'}，"
            f"仅支持: {', '.join(sorted(_ALLOWED_EXTS))}"
        )

    logger.info("上传文件: %s", safe_filename)

    token = str(uuid.uuid4())[:8]
    dest_dir = _UPLOADS_DIR / token
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_filename

    # 流式写入并检查大小
    total_size = 0
    with open(dest_path, "wb") as f:
        while chunk := await file.read(64 * 1024):  # 64KB chunks
            total_size += len(chunk)
            if total_size > _MAX_UPLOAD_SIZE:
                f.close()
                shutil.rmtree(dest_dir, ignore_errors=True)
                raise ValidationError(f"文件过大，最大支持 {_MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            f.write(chunk)

    logger.info("上传完成: %s (%d bytes)", safe_filename, total_size)
    return {
        "token": token,
        "filename": safe_filename,
        "size": total_size,
    }


@router.get("/download/{token}/{filename}")
def download_file(token: str, filename: str) -> FileResponse:
    """下载沙盒导出的文件。

    URL 格式: /api/download/{token}/{filename}
    token 和 filename 由 sandbox_export_file 工具生成。
    """
    # 清理 filename 防止路径穿越
    safe_filename = Path(filename).name
    file_path = _DOWNLOADS_DIR / token / safe_filename

    # 安全检查：防止路径穿越
    if not file_path.resolve().is_relative_to(_DOWNLOADS_DIR.resolve()):
        raise ForbiddenError("非法路径")

    if not file_path.is_file():
        raise NotFoundError("文件不存在或已过期")

    # 根据扩展名判断：图片/文本内联显示，其他强制下载
    ext = Path(safe_filename).suffix.lower()
    if ext in _INLINE_EXTS:
        # 内联显示：浏览器直接渲染图片/文本
        media_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        return FileResponse(
            path=str(file_path),
            filename=safe_filename,
            media_type=media_type,
        )

    # 强制下载
    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type="application/octet-stream",
    )
