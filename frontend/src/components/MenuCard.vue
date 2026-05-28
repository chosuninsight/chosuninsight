<template>
  <button class="menu-card" type="button" @click="$emit('click', label)">
    <component :is="icon" class="icon" :size="24" :color="iconColor" aria-hidden="true" />
    <span class="label">{{ label }}</span>
  </button>
</template>

<script setup>
defineProps({
  // icon: Object,
  icon: [Object, Function],
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

.menu-card:focus-visible {
  outline: 2px solid #2e86de;
  outline-offset: 2px;
}

.icon {
  flex-shrink: 0;
}

.label {
  font-size: 13px;
  color: #333;
  font-weight: 500;
}

@media (max-width: 480px) {
  .menu-card {
    width: 90px;
    min-width: 90px;
    flex-shrink: 0;
  }

  .label {
    font-size: 11px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .menu-card {
    transition-duration: 0.01ms;
  }

  .menu-card:hover {
    transform: none;
  }
}
</style>
