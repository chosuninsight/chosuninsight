<template>
  <header class="header">
    <div class="header-inner">
      <img :src="logoImg" alt="조선대학교 로고" class="logo-img" />
      <div class="header-text">
        <div class="logo">조선인사이트</div>
      </div>
    </div>
  </header>
</template>

<script setup>
import logoImg from '../assets/logo.png'
</script>

<style scoped>
.header {
  background: white;
  border-bottom: 1.0px solid #e8f2fb;
  padding: 16px 24px;
}

.header-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.logo-img {
  height: 28px;
  width: 28px;
  object-fit: contain;
}

.header-text {
  display: flex;
  flex-direction: column;
}

.logo {
  font-size: 22px;
  font-family: 'Noto Sans KR', sans-serif;
  font-weight: bold;
  letter-spacing: 1px;
  color: #3d3d3d;
}

.subtitle {
  font-size: 12px;
  margin-top: 2px;
  opacity: 0.85;
}
</style>
