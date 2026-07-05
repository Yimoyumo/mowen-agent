"""文件上传与下载路由。

上传: POST /api/upload → 文件暂存到 uploads/
下载: GET  /api/download/{token}/{filename} → 从 downloads/ 提供沙盒导出的文件
"""

import mimetypes
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter()

_DOWNLOADS_DIR = Path("downloads")
_UPLOADS_DIR = Path("uploads")
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 图片扩展名 → 浏览器内联显示（而非下载）
_INLINE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.txt', '.csv', '.json', '.md'}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """上传文件到暂存区，返回 file token 供 Agent 使用。

    前端上传文件后，将返回的 token + filename 加入 ChatRequest.uploaded_files，
    Agent 会自动将文件导入沙盒处理。
    """
    token = str(uuid.uuid4())[:8]
    dest_dir = _UPLOADS_DIR / token
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / (file.filename or "unnamed")

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "token": token,
        "filename": file.filename or "unnamed",
        "size": dest_path.stat().st_size,
    }


@router.get("/download/{token}/{filename}")
def download_file(token: str, filename: str) -> FileResponse:
    """下载沙盒导出的文件。

    URL 格式: /api/download/{token}/{filename}
    token 和 filename 由 sandbox_export_file 工具生成。
    """
    file_path = _DOWNLOADS_DIR / token / filename

    # 安全检查：防止路径穿越
    if not file_path.resolve().is_relative_to(_DOWNLOADS_DIR.resolve()):
        raise HTTPException(status_code=403, detail="非法路径")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")

    # 根据扩展名判断：图片/文本内联显示，其他强制下载
    ext = Path(filename).suffix.lower()
    if ext in _INLINE_EXTS:
        # 内联显示：浏览器直接渲染图片/文本
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=media_type,
        )

    # 强制下载
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )
