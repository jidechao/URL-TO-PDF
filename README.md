# URL2PDF

URL 转 PDF 工具，支持 JavaScript 动态渲染，提供两种输出模式：高保真还原与清洁排版。基于 Playwright + Chromium，自动处理懒加载、Shadow DOM、字体加载等现代网页特性。

## 核心特性

- **双模式输出**
  - `faithful`（高保真）：所见即所得，保留原始页面布局、样式、配色；纸张宽度匹配桌面视口（默认 1920px），不会因 A4 宽度触发移动端响应式布局
  - `clean`（清洁）：自动提取正文，去除导航栏/广告/评论等噪声，套用统一排版
  - `auto`（默认）：自动判断页面类型，文章页走 clean，非文章页走 faithful
- **JS 动态渲染**：完整支持 React / Vue / Next.js / Nuxt 等 SPA 框架
- **智能等待**：MutationObserver 检测 DOM 稳定，不依赖不可靠的 `networkidle`
- **懒加载处理**：自动滚动触发图片加载、无限滚动（三道硬上限防 OOM）
- **反爬虫**：最小 stealth 注入（去 webdriver 标志 + 真实 UA）
- **降级机制**：Canvas/WebGL 页面自动截图降级；clean 抽取失败自动回退 faithful
- **print 事件拦截**：阻止网站 `beforeprint` 回调重构 DOM（如 gov.cn 会导致内容重复/布局错乱）

## 安装

```bash
git clone <repo-url> URL2PDF
cd URL2PDF
python -m venv .venv
.venv\Scripts\activate  # Linux/macOS: source .venv/bin/activate
pip install -e .
playwright install chromium
```

## 快速开始

### 命令行

```bash
# 默认 auto 模式
python -m url2pdf https://example.com -o output.pdf

# 指定模式
python -m url2pdf https://example.com --mode clean -o article.pdf
python -m url2pdf https://example.com --mode faithful -o snapshot.pdf

# faithful 模式隐藏 cookie 横幅
python -m url2pdf https://example.com --mode faithful --hide-noise -o clean-snapshot.pdf

# 注入 Cookie（访问需要登录的页面）
python -m url2pdf https://example.com/private --cookies '[{`"name`":`"session`",`"value`":`"xxx`",`"url`":`"https://example.com`"}]'
```

### Python 库

```python
import asyncio
from url2pdf import convert

async def main():
    pdf = await convert("https://example.com", mode="auto", output_path="output.pdf")
    print(f"生成 {`len(pdf)`} bytes")

asyncio.run(main())
```

## 三种模式对比

| 维度 | faithful | clean | auto |
|------|----------|-------|------|
| 是否提取正文 | 否 | 是 | 自动判断 |
| CSS 来源 | 原站点 | 统一排版 | 视判定结果 |
| 还原度 | 最高 | 牺牲原外观换可读性 | - |
| 适用场景 | 存档、页面快照、非文章页 | RAG/知识库、文章归档 | 通用默认 |
| 去噪 | 可选 --hide-noise | 自动 | - |

auto 判定逻辑：用 trafilatura 试抽纯文本，长度超过 800 字符则走 clean，否则走 faithful。

## API 参数

```python
await convert(
    url: str,                          # 目标 URL
    mode: str = "auto",                # "faithful" | "clean" | "auto"
    cookies: list[dict] | None = None, # Playwright 格式的 Cookie 列表
    hide_noise: bool = False,          # 仅 faithful：隐藏 cookie/consent 横幅
    output_path: str | None = None,    # 给定则写文件，否则只返回 bytes
    timeout_ms: int = 30000,           # 页面超时（毫秒）
    pool: BrowserPool | None = None,   # 自定义浏览器池（默认用单例）
) -> bytes
```

## 关键技术决策

**不用 networkidle**：常驻轮询、SSE、WebSocket 会让它永不触发或过早触发。改用 domcontentloaded + load + MutationObserver 组合。

**setContent 后等资源就绪**：clean 模式 setContent 后，必须等 document.fonts.ready + 图片 complete，否则 PDF 出现空白图/回退字体。

**Shadow DOM 递归展开**：clean 模式抽取前，把 shadowRoot 内的 style 和子节点克隆到 light DOM，否则 trafilatura 看不到 shadow 内容。

**无限滚动三道硬上限**：最大滚动轮次（50）、最大 DOM 节点数（5000）、最大文档高度（50000px），任一触发即停。

**标题去重**：trafilatura 的 body_html 已含标题，build_clean_html 检测前 100 字符窗口，标题已存在则不重复加 h1。

**beforeprint 事件拦截**：部分站点（如 gov.cn）在 beforeprint 回调中重构 DOM（压缩 header、克隆内容、固定像素宽度），导致 page.pdf 输出重复或错乱。在页面脚本执行前注入 stopImmediatePropagation 拦截该事件。

**纸张宽度匹配视口**：Chromium 的 page.pdf 按纸张宽度而非浏览器视口布局。A4（210mm 减边距约 680px）低于 768px 响应式断点，网站会切换成移动端布局（导航栏折叠、多列堆叠）。faithful 模式把纸张宽度设为视口宽度（保持 A4 的 210:297 比例），确保按桌面端布局渲染。

**吸顶导航还原**：自动滚动到底部会触发 sticky-on-scroll 导航（滚动时加 fixed 类悬浮），打印时遮盖页面头部。滚动结束后先回到页面顶部让导航恢复文档流位置；对始终 fixed 的元素，打印前统一转为 absolute，避免 Chromium 把悬浮元素重复输出到每一页造成遮盖（元素保持可见，不删除任何内容）。

**Canvas/WebGL 截图降级**：page.pdf 对复杂 Canvas/WebGL 矢量化效果差，输出过小（小于 5KB）时自动降级为全页截图拼 PDF。

## 项目结构

```text
url2pdf/
├── __init__.py        # 导出 convert
├── browser.py         # 浏览器池复用 + stealth
├── render.py          # DOM 稳定检测 / 滚动 / 资源等待 / beforeprint 拦截
├── extract.py         # trafilatura 主力 + readability-lxml 兜底 + auto 启发式
├── pdf.py             # faithful / clean / 截图降级 + 统一 Print CSS
├── core.py            # convert 编排
└── __main__.py        # CLI 入口
tests/
├── test_pipeline.py   # 单元 + 端到端测试
└── fixtures/          # article.html / landing.html / printtrap.html
```

## 运行测试

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

## 依赖

- playwright（含 Chromium）
- trafilatura
- readability-lxml
- lxml

Python >= 3.10。

## 已知限制

- adoptedStyleSheets（constructable stylesheets）无法提取文本，Shadow DOM 展开时样式可能不完整
- 复杂 Cloudflare/Akamai 挑战页可能被拦截（只做了基础 stealth，未集成商业代理）
- 截图降级 PDF 无可选文本（光栅化）
- HTTP 服务接口未实现（当前只有 CLI + 库）

## License

MIT
