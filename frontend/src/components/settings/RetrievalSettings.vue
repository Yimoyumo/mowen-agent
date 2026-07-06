<script setup lang="ts">
import { ref, watch } from 'vue'
import type { UserSettings } from '@/types/api'

interface Props {
  settings: UserSettings
  saving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  save: [updates: Partial<UserSettings>]
}>()

// 本地编辑状态
const topK = ref(props.settings.retrieval.top_k)
const queryExpansion = ref(props.settings.retrieval.query_expansion)

// 同步 props 变化
watch(
  () => props.settings,
  (newVal) => {
    topK.value = newVal.retrieval.top_k
    queryExpansion.value = newVal.retrieval.query_expansion
  },
)

function handleSave() {
  emit('save', {
    retrieval: {
      top_k: topK.value,
      query_expansion: queryExpansion.value,
    },
  } as any)
}

// top_k 是否使用默认值
const useDefaultTopK = ref(topK.value === 0)
const useDefaultExpansion = ref(queryExpansion.value === null)

watch(useDefaultTopK, (val) => {
  if (val) topK.value = 0
})

watch(useDefaultExpansion, (val) => {
  if (val) queryExpansion.value = null
})
</script>

<template>
  <div class="retrieval-settings">
    <h2 class="section-title">检索参数</h2>
    <p class="section-desc">控制 RAG 知识库检索的行为，影响召回结果的数量和质量。</p>

    <el-card shadow="never" class="settings-card">
      <!-- top_k -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">召回数量 (top_k)</span>
          <span class="label-desc">从知识库中检索返回的文档片段数量</span>
        </div>
        <div class="setting-control">
          <el-checkbox v-model="useDefaultTopK">使用默认值</el-checkbox>
          <el-slider
            v-if="!useDefaultTopK"
            v-model="topK"
            :min="1"
            :max="50"
            show-input
            :show-input-controls="false"
            style="margin-top: 8px"
          />
          <div v-if="!useDefaultTopK" class="slider-tip">
            数量越多，上下文越丰富，但可能引入噪声；通常 10~20 较为合适。
          </div>
        </div>
      </div>

      <el-divider />

      <!-- 查询扩写 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">查询扩写</span>
          <span class="label-desc">使用 LLM 扩展查询关键词，提高召回率</span>
        </div>
        <div class="setting-control">
          <el-checkbox v-model="useDefaultExpansion">使用默认值</el-checkbox>
          <el-switch
            v-if="!useDefaultExpansion"
            v-model="queryExpansion"
            active-text="开启"
            inactive-text="关闭"
            style="margin-top: 8px"
          />
          <div v-if="!useDefaultExpansion" class="slider-tip">
            开启后，LLM 会生成查询的多个变体来增强检索效果。
          </div>
        </div>
      </div>

      <el-divider />

      <div class="save-area">
        <el-button type="primary" :loading="saving" @click="handleSave">
          保存
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px;
}

.section-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 20px;
}

.settings-card {
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.setting-item {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.setting-label {
  min-width: 180px;
  flex-shrink: 0;
}

.label-text {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.label-desc {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.setting-control {
  flex: 1;
  min-width: 0;
}

.slider-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.save-area {
  display: flex;
  justify-content: flex-end;
}
</style>
