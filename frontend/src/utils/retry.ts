import { ElMessage } from 'element-plus'

// 后端同步失败后重试等待时间序列（毫秒），最多重试 3 次
const RETRY_DELAYS = [1000, 3000, 8000]

/** 带重试 + 错误提示的异步调用包装。
 *  - 失败时自动重试，避免后端瞬时抖动导致数据丢失
 *  - 最终失败时 toast 提示用户，并返回 false
 *  - mute=true 时只重试不弹窗，用于后台/流式同步场景
 */
export async function callWithRetry<T>(
  fn: () => Promise<T>,
  mute = false,
  retries = RETRY_DELAYS.length,
): Promise<boolean> {
  for (let i = 0; i <= retries; i++) {
    try {
      await fn()
      return true
    } catch (e) {
      if (i === retries) {
        if (!mute) {
          const msg = e instanceof Error ? e.message : String(e)
          console.error('[chat sync] 最终失败:', msg, e)
          ElMessage.warning(`同步后端失败：${msg}。本次操作仅保留在本地。`)
        }
        return false
      }
      const delay = RETRY_DELAYS[i] ?? 5000
      console.warn(`[chat sync] 失败，${delay}ms 后重试 (${i + 1}/${retries}):`, e)
      await new Promise(r => setTimeout(r, delay))
    }
  }
  return false
}
