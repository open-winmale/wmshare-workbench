/// <reference types="vite/client" />

import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],

  // 相对 base：产物可由后端在任意子路径托管（同源单端口）。
  // 配合 hash 路由，后端只需托管 / 与 /assets/*，无需 SPA fallback。
  base: "./",

  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },

  build: {
    // 产物直接写进 Python 包 —— 无拷贝步骤、无产物交接。
    // 照搬 wmshare-tools 的做法：vite outDir 指向包内目录。
    outDir: fileURLToPath(
      new URL("../backend/workbench/static", import.meta.url),
    ),
    // outDir 在项目根之外，vite 默认不清理；显式打开避免旧 hash 文件堆积
    emptyOutDir: true,

    // 把 echarts 拆成独立 chunk：它是体积大头，且**几乎不变**。
    // 与应用代码同包会让每次改业务代码都让用户重下整个图表库；
    // 拆开后各 chunk 带自己的 hash，`immutable` 长缓存才真正生效。
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ["echarts/core", "echarts/charts", "echarts/components",
            "echarts/renderers"],
          vue: ["vue"],
        },
      },
    },
  },

  server: {
    port: 5173,
    // 开发时前端跑 vite dev server，API 代理到本地后端（两进程）
    proxy: {
      "/api": { target: "http://127.0.0.1:8787", changeOrigin: false },
    },
  },
});
