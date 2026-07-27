# URL 转 PDF 技术方案（支持 JS 动态渲染、正文抽取与高保真还原）

## 1. 项目背景

随着知识库构建、RAG 检索、企业内容归档等场景的发展，越来越多的业务需要将网页（URL）转换为高质量 PDF。

传统方案（wkhtmltopdf、requests + BeautifulSoup）存在以下问题：

- 不支持 JavaScript 动态渲染（React、Vue、Next.js 等）
- HTML 标签噪声严重（导航栏、广告、评论区、Footer 等）
- PDF 排版混乱，可读性差
- 图片、字体、CSS 丢失
- 无法正确处理懒加载、无限滚动等现代网页

因此，需要设计一套支持现代 Web 的 **URL → PDF** 技术方案，实现：

- 支持 JS 动态渲染
- 自动提取正文内容
- 去除 HTML 噪声
- 保留页面视觉效果
- 输出高质量 PDF

---

# 2. 总体架构

```text
                  URL
                   │
                   ▼
      ┌────────────────────┐
      │ Playwright Browser │
      │ (Chromium Headless)│
      └─────────┬──────────┘
                │
                ▼
      JS 动态渲染 + DOM 稳定检测
                │
                ▼
      自动滚动（Lazy Load）
                │
                ▼
      Shadow DOM / iframe 处理
                │
                ▼
       获取最终 Render DOM
                │
                ▼
      Readability 正文抽取
                │
                ▼
      DOM 清洗（去噪）
                │
                ▼
      CSS 重排（Print Layout）
                │
                ▼
        浏览器重新渲染
                │
                ▼
             PDF 输出
```

---

# 3. 技术选型

| 模块 | 推荐方案 | 作用 |
|-------|----------|------|
| 浏览器 | Playwright | JS 渲染 |
| 浏览器内核 | Chromium | 高兼容 |
| DOM 获取 | page.content() | 获取 Render 后 HTML |
| 正文提取 | Mozilla Readability | 去噪 |
| HTML 清洗 | BeautifulSoup / lxml | 删除无效节点 |
| CSS 重排 | Print CSS | 美化 PDF |
| PDF | Playwright page.pdf() | 高保真输出 |

---

# 4. 技术流程

## Step1 浏览器加载页面

采用 Playwright 打开网页。

```python
await page.goto(
    url,
    wait_until="networkidle"
)
```

浏览器将：

- 下载 HTML
- 下载 CSS
- 执行 JavaScript
- 请求 Ajax
- 渲染最终 DOM

相比 requests，可完整支持：

- React
- Vue
- Angular
- Next.js
- Nuxt
- SPA

---

## Step2 页面稳定检测

仅依赖 `networkidle` 并不能代表页面已经完成渲染。

推荐采用多策略组合：

```text
networkidle

↓

MutationObserver

↓

DOM 无变化 2 秒

↓

最长等待 15 秒
```

判断页面真正完成加载。

优势：

- Ajax 页面
- 延迟加载
- SPA 页面

均能稳定支持。

---

## Step3 自动滚动

现代网站大量采用：

- Lazy Image
- Infinite Scroll

因此需要模拟用户滚动。

```text
滚动到底

↓

等待加载

↓

继续滚动

↓

直到高度不再变化
```

可确保：

- 图片加载完成
- 长文章全部展开
- 评论按需加载（可选择关闭）

---

## Step4 获取最终 DOM

不要解析原始 HTML。

应获取浏览器 Render 后 DOM。

```python
html = await page.content()
```

例如：

原始 HTML：

```html
<div id="root"></div>
```

Render 后：

```html
<div id="root">

<article>

......

</article>

</div>
```

这是现代网页最关键的一步。

---

# 5. 正文抽取（Content Extraction）

网页最大的噪声来源不是 HTML，而是：

- Header
- Navigation
- Sidebar
- Footer
- 评论区
- 推荐阅读
- Cookie Banner
- 广告

推荐使用：

Mozilla Readability

自动识别：

- 标题
- 作者
- 发布时间
- 正文
- 图片
- Caption

自动删除：

- nav
- aside
- footer
- menu
- comments
- share button
- ads

相比 XPath、CSS Selector，准确率更高。

---

# 6. DOM 清洗

Readability 后再次清洗 DOM。

删除：

```text
script

style

noscript

iframe

tracking

svg 广告

display:none

visibility:hidden

aria-hidden
```

同时：

统一图片地址

下载字体

下载 CSS

保证 PDF 离线可阅读。

---

# 7. Print CSS 重排

不要直接打印网页。

建议重新生成统一 HTML：

```html
<html>

<head>

统一 Print CSS

</head>

<body>

正文

</body>

</html>
```

推荐样式：

- A4
- 左右留白
- 最大宽度 820px
- 图片宽度 100%
- 自动分页
- 代码高亮
- 表格自动分页

例如：

```css
body{

max-width:820px;

margin:auto;

font-family:

"Noto Sans SC",

sans-serif;

line-height:1.8;

}
```

最终 PDF 更接近：

- Medium
- Notion Export
- ChatGPT Deep Research

阅读体验远优于浏览器打印。

---

# 8. PDF 输出

重新加载清洗后的 HTML：

```python
await page.setContent(clean_html)

await page.pdf()
```

生成 PDF。

推荐参数：

```python
page.pdf(

format="A4",

print_background=True,

margin={

"top":"15mm",

"bottom":"15mm",

"left":"15mm",

"right":"15mm"

}

)
```

---

# 9. 特殊场景处理

## 9.1 React / Vue

无需特殊处理。

Playwright 自动执行：

- React
- Vue
- Next.js
- Nuxt

等待 DOM 稳定即可。

---

## 9.2 Ajax

推荐监听：

MutationObserver

而不是：

```python
sleep(5)
```

DOM 连续稳定后导出。

---

## 9.3 Lazy Load

自动滚动页面。

确保：

```text
图片

Canvas

SVG

全部加载完成
```

---

## 9.4 无限滚动

持续：

```text
scroll

↓

等待

↓

scroll

↓

页面高度不再变化

↓

结束
```

---

## 9.5 Shadow DOM

递归展开：

```javascript
shadowRoot
```

将 Shadow 内容复制到普通 DOM。

否则正文会缺失。

---

## 9.6 iframe

同源 iframe：

进入解析。

跨域 iframe：

保留 iframe

或截图。

---

## 9.7 MathJax / KaTeX

等待：

```javascript
MathJax.typesetPromise()
```

完成。

保证公式正确渲染。

---

## 9.8 Mermaid

等待：

```javascript
mermaid.run()
```

完成。

保证流程图正常显示。

---

## 9.9 Canvas / ECharts

等待：

Canvas 渲染完成。

浏览器导出即可。

---

# 10. 异常处理

建议增加：

- 页面超时
- DNS 失败
- JS 崩溃
- 图片加载失败
- 字体下载失败
- 页面跳转
- 登录页面检测

支持：

- Retry
- Timeout
- 降级导出

---

# 11. 性能优化

建议采用浏览器池：

```text
Browser Pool

├── Browser1

├── Browser2

├── Browser3

└── BrowserN
```

避免频繁启动 Chromium。

优化：

- Browser 复用
- Context 复用
- Page 复用
- 图片缓存
- CSS 缓存
- 字体缓存

支持高并发 URL 转 PDF。

---

# 12. 最终流程

```text
                 URL
                  │
                  ▼
      Playwright Browser Pool
                  │
                  ▼
        JS 动态渲染
                  │
                  ▼
      DOM 稳定检测（Mutation）
                  │
                  ▼
      自动滚动（Lazy Load）
                  │
                  ▼
      Shadow DOM / iframe
                  │
                  ▼
       获取最终 Render DOM
                  │
                  ▼
      Readability 正文抽取
                  │
                  ▼
      DOM 清洗（广告、导航）
                  │
                  ▼
      Print CSS 排版
                  │
                  ▼
      浏览器重新渲染 HTML
                  │
                  ▼
        Playwright PDF
                  │
                  ▼
             PDF 输出
```

---

# 13. 技术优势

| 能力 | 本方案 | 传统 HTML→PDF |
|------|--------|---------------|
| JavaScript 渲染 | ✅ | ❌ |
| React/Vue 支持 | ✅ | ❌ |
| Ajax 页面 | ✅ | ❌ |
| Lazy Load | ✅ | ❌ |
| Infinite Scroll | ✅ | ❌ |
| Readability 正文抽取 | ✅ | ❌ |
| 自动去广告 | ✅ | ❌ |
| 自动去导航 | ✅ | ❌ |
| Print CSS 美化 | ✅ | 一般 |
| 高保真 PDF | ✅ | 一般 |
| 企业级可扩展 | ✅ | 较差 |

---

# 14. 总结

本方案采用 **Playwright + Chromium + Readability + DOM 清洗 + Print CSS + PDF** 的技术路线，兼顾现代 Web 的动态渲染能力与文档输出质量。相比传统 HTML→PDF 方案，能够完整支持 React、Vue、Next.js 等前端框架，自动去除导航栏、广告、评论等页面噪声，并通过统一排版输出高保真、可阅读、适合归档和知识库构建的 PDF，是目前企业级 URL 转 PDF 的推荐实现方案。