<script setup lang="ts">
const props = defineProps<{ label: string; value: number | null | undefined }>()

const R = 28
const C = 2 * Math.PI * R
const pct = computed(() => Math.max(0, Math.min(100, Math.round(props.value ?? 0))))
const color = computed(() => props.value == null ? 'text-muted' : pct.value >= 80 ? 'text-emerald-500' : pct.value >= 60 ? 'text-amber-500' : 'text-red-500')
</script>

<template>
  <Card class="flex-row items-center gap-3 px-4 py-3">
    <svg viewBox="0 0 64 64" class="size-14 -rotate-90" role="img" :aria-label="`${label}: ${value == null ? 'chưa có' : pct + '%'}`">
      <circle cx="32" cy="32" :r="R" fill="none" stroke="currentColor" stroke-width="6" class="text-muted" />
      <circle
        cx="32" cy="32" :r="R" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round"
        :class="color" :stroke-dasharray="C" :stroke-dashoffset="C * (1 - pct / 100)"
        class="transition-[stroke-dashoffset] duration-500"
      />
    </svg>
    <div>
      <div class="text-2xl font-semibold tabular-nums">{{ value == null ? '—' : `${pct}%` }}</div>
      <div class="text-xs text-muted-foreground">{{ label }}</div>
    </div>
  </Card>
</template>
