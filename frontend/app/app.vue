<script setup lang="ts">
import { MoreVertical, Plus, Send, Trash2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { AGENTS, TONES } from '@/lib/format'

const { data: contents, refresh: refreshContents } = await useFetch<any[]>('/api/contents?limit=1000', { default: () => [] })

const topic = ref('')
const tone = ref('friendly')
const selectedId = ref<number | null>(null)
const content = ref<any>(null)
const job = ref<any>(null) // job đang chạy (từ SSE), ưu tiên hơn job cũ của bài đang xem
let es: EventSource | null = null

const steps = computed(() => job.value?.steps ?? content.value?.jobs?.at(-1)?.steps ?? [])
const progress = computed(() => {
  if (!job.value && !content.value) return null
  return 100 * new Set(steps.value.filter((s: any) => s.status === 'done').map((s: any) => s.agent)).size / AGENTS.length
})

const seoText = computed(() => {
  const c = content.value
  return c ? `Từ khoá chính: ${c.focus_keyword}
Meta title: ${c.meta_title}
Meta description: ${c.meta_description}
Slug: ${c.slug}
Từ khoá phụ: ${c.keywords?.join(', ')}` : ''
})

async function select(id: number) {
  selectedId.value = id
  try {
    content.value = await $fetch(`/api/contents/${id}`)
  } catch (e: any) {
    toast.error(e?.data?.detail ?? 'Không tải được bài viết')
  }
}

function newBlank() { selectedId.value = null; content.value = null; topic.value = '' }

async function remove(id: number) {
  try {
    await $fetch(`/api/contents/${id}`, { method: 'DELETE' })
  } catch (e: any) {
    return toast.error(e?.data?.detail ?? 'Không xóa được bài')
  }
  if (id === selectedId.value) { selectedId.value = null; content.value = null }
  await refreshContents()
}

async function submit() {
  if (!topic.value.trim()) return
  try {
    job.value = await $fetch('/api/jobs', { method: 'POST', body: { topic: topic.value.trim(), tone: tone.value } })
  } catch (e: any) {
    return toast.error(e?.data?.detail ?? 'Không tạo được job')
  }
  topic.value = ''
  refreshContents() // bài mới xuất hiện ngay trong sidebar
  content.value = null
  selectedId.value = null
  es?.close()
  es = new EventSource(`/api/jobs/${job.value.id}/events`)
  es.addEventListener('snapshot', (e) => { job.value = JSON.parse((e as MessageEvent).data) })
  es.addEventListener('end', async (e) => {
    es?.close()
    const done = (e as MessageEvent).data === 'done'
    done ? toast.success('Đã viết xong') : toast.error(job.value?.error || 'Job lỗi')
    await refreshContents()
    if (job.value?.content_id) await select(job.value.content_id)
    job.value = null
  })
  es.onerror = () => { es?.close(); toast.error('Mất kết nối tiến trình') }
}

onBeforeUnmount(() => es?.close())
</script>

<template>
  <div class="flex h-dvh flex-col overflow-hidden bg-background md:flex-row">
    <aside class="flex shrink-0 flex-col border-b bg-muted/40 max-md:h-56 md:w-72 md:border-r md:border-b-0">
      <div class="flex items-center justify-between p-4 pr-3 font-semibold">
        Content Agent
        <Button variant="ghost" size="icon" class="size-7" aria-label="Bài mới" title="Bài mới" @click="newBlank"><Plus class="size-4" /></Button>
      </div>
      <ScrollArea class="min-h-0 flex-1">
        <ul class="space-y-1 px-2 pb-4">
          <li v-for="c in contents" :key="c.id" class="relative">
            <button
              class="w-full rounded-md py-2 pr-10 pl-3 text-left text-sm hover:bg-accent"
              :class="{ 'bg-accent': c.id === selectedId }"
              @click="select(c.id)"
            >
              <div class="line-clamp-2 font-medium">{{ c.topic }}</div>
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="ghost" size="icon" class="absolute top-1.5 right-1 size-7 text-muted-foreground" aria-label="Tùy chọn">
                  <MoreVertical class="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem variant="destructive" @select="remove(c.id)"><Trash2 class="size-4" />Xóa</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </li>
          <li v-if="!contents.length" class="px-3 text-sm text-muted-foreground">Chưa có bài nào.</li>
        </ul>
      </ScrollArea>
    </aside>

    <main class="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto p-4 md:p-6">
      <form class="flex gap-2" @submit.prevent="submit">
        <Input v-model="topic" placeholder="Nhập chủ đề bài viết…" aria-label="Chủ đề" :disabled="!!job" class="flex-1" />
        <Select v-model="tone">
          <SelectTrigger class="w-40" aria-label="Giọng văn"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="t in TONES" :key="t.value" :value="t.value">{{ t.label }}</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" :disabled="!!job || !topic.trim()"><Send class="size-4" />Viết</Button>
      </form>

      <Pipeline :steps="steps" />

      <div class="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Ring label="Tiến độ pipeline" :value="progress" />
        <Ring label="Điểm SEO" :value="content?.seo_score" />
        <Ring label="Độ dễ đọc" :value="content?.readability_score" />
      </div>

      <div v-if="content" class="space-y-3">
        <h1 class="text-lg font-semibold">{{ content.meta_title || content.topic }}</h1>
        <Tabs default-value="blog">
          <TabsList>
            <TabsTrigger value="blog">Blog</TabsTrigger>
            <TabsTrigger value="social">Social</TabsTrigger>
            <TabsTrigger value="seo">SEO</TabsTrigger>
          </TabsList>
          <TabsContent value="blog">
            <Card class="relative p-6 pr-12"><CopyBtn :text="content.blog_md" /><article class="prose-lite"><MDC :value="content.blog_md" /></article></Card>
          </TabsContent>
          <TabsContent value="social" class="space-y-3">
            <Card v-for="(text, p) in content.social" :key="p" class="relative gap-2 p-4 pr-12">
              <CopyBtn :text="text" />
              <div class="text-sm font-medium capitalize">{{ p }}</div>
              <p class="whitespace-pre-wrap text-sm">{{ text }}</p>
            </Card>
          </TabsContent>
          <TabsContent value="seo">
            <Card class="relative gap-2 p-4 pr-12 text-sm">
              <CopyBtn :text="seoText" />
              <p><b>Từ khoá chính:</b> {{ content.focus_keyword || '—' }}</p>
              <p><b>Meta title:</b> {{ content.meta_title || '—' }}</p>
              <p><b>Meta description:</b> {{ content.meta_description || '—' }}</p>
              <p><b>Slug:</b> {{ content.slug || '—' }}</p>
              <p><b>Từ khoá phụ:</b> {{ content.keywords?.join(', ') || '—' }}</p>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
      <p v-else-if="!job" class="text-sm text-muted-foreground">Chọn một bài bên trái hoặc nhập chủ đề để bắt đầu.</p>
    </main>
  </div>
  <Toaster position="top-center" rich-colors />
</template>
