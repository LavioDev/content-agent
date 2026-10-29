import tailwindcss from '@tailwindcss/vite'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  ssr: false, // dashboard cục bộ, không cần SSR
  modules: ['shadcn-nuxt', '@nuxtjs/color-mode', '@vueuse/nuxt', '@nuxtjs/mdc'],
  css: ['~/assets/css/tailwind.css'],
  vite: { plugins: [tailwindcss()] },
  colorMode: { classSuffix: '', preference: 'system', fallback: 'light' },
  shadcn: { prefix: '', componentDir: './app/components/ui' },
  // Frontend chỉ nói chuyện với backend qua proxy; không bao giờ giữ API key LLM
  routeRules: { '/api/**': { proxy: 'http://127.0.0.1:8787/api/**' } },
  app: {
    head: {
      title: 'Content Agent',
      htmlAttrs: { lang: 'vi' },
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' },
      ],
    },
  },
})
