---
version: 1
default_provider: dashscope
default_quality: 2k
default_aspect_ratio: "16:9"
default_model:
  google: null
  openai: null
  openrouter: "google/gemini-3.1-flash-image-preview"
  dashscope: "qwen-image-2.0-pro"
  replicate: null
batch:
  max_workers: 3
  provider_limits:
    dashscope:
      concurrency: 2
      start_interval_ms: 1200
---
