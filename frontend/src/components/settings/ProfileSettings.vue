<script setup lang="ts">
import { ref, watch } from 'vue'
import type { UserProfile } from '@/types/api'

interface Props {
  profile: UserProfile
  saving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  save: [profile: UserProfile]
}>()

const skills = ref(props.profile.skills)
const interests = ref(props.profile.interests)
const preferences = ref(props.profile.preferences)

watch(
  () => props.profile,
  (newVal) => {
    skills.value = newVal.skills
    interests.value = newVal.interests
    preferences.value = newVal.preferences
  },
)

function handleSave() {
  emit('save', {
    skills: skills.value,
    interests: interests.value,
    preferences: preferences.value,
  })
}
</script>

<template>
  <div class="profile-settings">
    <h2 class="section-title">用户画像</h2>
    <p class="section-desc">
      告诉 AI 助手关于你的信息，帮助它提供更贴合你需求的回答。
      这些信息会注入到系统提示词中。
    </p>

    <el-card shadow="never" class="settings-card">
      <el-form label-position="top" label-width="auto">
        <el-form-item label="技能">
          <el-input
            v-model="skills"
            placeholder="你的专业技能，如：Python, 机器学习, 前端开发"
          />
          <div class="field-tip">
            告诉助手你擅长什么，它会据此调整回答深度
          </div>
        </el-form-item>

        <el-form-item label="兴趣">
          <el-input
            v-model="interests"
            placeholder="你的兴趣领域，如：开源项目, 技术写作, 区块链"
          />
          <div class="field-tip">
            助手会在相关话题上提供更多延伸信息
          </div>
        </el-form-item>

        <el-form-item label="偏好">
          <el-input
            v-model="preferences"
            type="textarea"
            :rows="3"
            placeholder="你希望助手如何回答，如：回答要简洁、多用代码示例、先给结论再展开"
          />
          <div class="field-tip">
            回答风格、格式偏好等
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">
            保存
          </el-button>
        </el-form-item>
      </el-form>
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
  line-height: 1.6;
}

.settings-card {
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.field-tip {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 4px;
}
</style>
