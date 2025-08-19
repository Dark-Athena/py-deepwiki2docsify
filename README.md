# DeepWiki to Docsify Converter

🚀 一个强大的工具，能够将 DeepWiki 在线项目页面完整转换为多语言 Docsify 文档站点。

## ✨ 功能特性

- 🔍 **智能内容提取**：自动爬取并完整提取 DeepWiki 页面内容
- 📄 **完整页面抓取**：支持提取站点中的所有页面（本项目测试提取了23个页面）
- 🧩 **复杂解析处理**：使用字符级解析处理嵌套引号和复杂 JSON 结构
- 🌐 **多语言支持**：自动生成中英文双语版本的 Docsify 项目（仅生成目录结构，暂未翻译）
- 📊 **图表支持**：完整支持 Mermaid 图表渲染
- 🎨 **丰富插件**：集成搜索、图片缩放、代码复制、分页等实用插件
- 🔗 **正确路由**：完美解决多语言项目中的路由和侧边栏问题
- 📱 **响应式界面**：优雅的语言切换功能和现代化UI

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 基本使用

```bash
# 生成单语言项目
python deepwiki2docsify.py "https://deepwiki.com/username/project" -o output_dir

# 生成多语言项目（推荐）
python deepwiki2docsify.py "https://deepwiki.com/username/project" -o output_dir --multilingual
```

### 3. 启动本地预览

```bash
cd output_dir
python -m http.server 3000
# 访问 http://localhost:3000
```

## 📋 命令行参数

- `URL`: DeepWiki 项目的在线页面 URL（必需）
- `-o, --output`: 输出目录名称（可选）
- `--multilingual`: 生成多语言版本（推荐）
- `--use-selenium / --no-selenium`: 是否使用 Selenium 处理动态内容
- `--help`: 显示帮助信息

## 🌍 多语言项目结构

```
output_dir/
├── index.html              # 主入口页面，支持语言切换
├── README.md               # 项目根页面
├── _sidebar.md             # 语言选择导航
├── .nojekyll              # GitHub Pages 配置
├── zh-cn/                 # 中文版本
│   ├── README.md          # 中文首页
│   ├── _sidebar.md        # 中文导航
│   └── pages/             # 中文页面内容
├── en/                    # 英文版本
│   ├── README.md          # 英文首页
│   ├── _sidebar.md        # 英文导航
│   └── pages/             # 英文页面内容
└── assets/                # 共享资源文件
    └── images/            # 图片资源
```

## 🔧 技术特点

### 智能内容解析
- **字符级解析**：逐字符分析JSON数据，完美处理嵌套引号和特殊字符
- **完整提取**：解决了只能提取1个页面的问题，成功提取所有23个页面
- **内容完整性**：避免因正则表达式失败导致的内容截断

### 多语言路由配置
- **正确的侧边栏路径**：使用完整语言前缀路径（如 `zh-cn/pages/...`）
- **Homepage设置**：默认加载中文版本首页
- **Alias配置**：完整的路径映射解决404问题
- **语言切换**：流畅的中英文切换体验

### 现代化功能
- **Mermaid图表**：完整支持复杂图表渲染
- **搜索功能**：支持中英文全文搜索
- **图片缩放**：点击图片可放大查看
- **代码复制**：一键复制代码块
- **分页导航**：便捷的上下页导航

## 🎯 使用示例

```bash
# 转换DeepWiki项目为多语言Docsify站点
python deepwiki2docsify.py \
  "https://deepwiki.com/Dark-Athena/PlsqlRewrite4GaussDB-web" \
  -o "my_docs" \
  --multilingual

# 转换完成后启动本地服务
cd my_docs
python -m http.server 3000

# 浏览器访问 http://localhost:3000
```

## 🌐 部署到 GitHub Pages

1. 将生成的项目内容推送到 GitHub 仓库
2. 在仓库设置中启用 GitHub Pages
3. 选择从根目录或 docs 目录部署
4. GitHub 会自动生成访问链接

## 🛠️ 核心依赖

- `requests` - HTTP请求处理
- `beautifulsoup4` - HTML解析
- `selenium` - 动态内容处理（可选）
- `webdriver-manager` - 浏览器驱动管理
- `click` - 命令行界面
- `markdownify` - HTML到Markdown转换

## 🎉 项目亮点

这个工具是经过实际项目验证的完整解决方案：

- ✅ **内容完整性**：成功解决了复杂JSON解析问题
- ✅ **多语言支持**：完美的中英文双语站点生成（仅生成目录结构，暂未翻译）
- ✅ **路由正确性**：解决了Docsify多语言路由的所有痛点
- ✅ **功能丰富性**：集成了现代文档站点的所有必要功能
- ✅ **使用简便性**：一条命令生成完整的文档站点
