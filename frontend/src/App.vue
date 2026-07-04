<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <RouterView />
</template>

<style>
* {
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
  margin: 0;
}

body {
  font-family:
    Inter,
    -apple-system,
    BlinkMacSystemFont,
    'PingFang SC',
    'Hiragino Sans GB',
    'Microsoft YaHei',
    '微软雅黑',
    Arial,
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
