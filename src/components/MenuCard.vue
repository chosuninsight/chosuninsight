<template>
  <button class="menu-card" @click="$emit('click', label)">
    <component :is="icon" class="icon" :size="24" :color="iconColor" />
    <span class="label">{{ label }}</span>
  </button>
</template>

<script setup>
defineProps({
  icon: Object,
  label: String,
  iconColor: String,
})
defineEmits(['click'])
</script>

<style scoped>
.menu-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 8px;
  background: white;
  border: 1.5px solid #d0e6f8;
  border-radius: 16px;
  cursor: pointer;
  font-family: inherit;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.07);
  transition: transform 0.18s, box-shadow 0.18s;
  width: 100%;
}

.menu-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.13);
}

.icon {
  flex-shrink: 0;
}

.label {
  font-size: 13px;
  color: #333;
  font-weight: 500;
}
</style>
