#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepWiki to Docsify Converter 
专门处理 DeepWiki 生成的在线页面，转换为 Docsify 项目
Copyright (C) <2025-2028>  <darkathena@qq.com>
"""

import os
import re
import sys
import json
import time
import click
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import logging

# 尝试导入 Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DeepWikiToDocsifyConverter:
    """DeepWiki 到 Docsify 转换器"""
    
    def __init__(self, base_url: str, output_dir: str = "./docs", use_selenium: bool = True, multilingual: bool = False, force_overwrite: bool = False):
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.multilingual = multilingual
        self.force_overwrite = force_overwrite
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        })
        self.driver = None
        
        # 检查输出目录
        self._check_output_directory()
        
        # 创建输出目录
        self.output_dir.mkdir(exist_ok=True)
        if self.multilingual:
            # 多语言目录结构
            (self.output_dir / "zh-cn").mkdir(exist_ok=True)
            (self.output_dir / "zh-cn" / "pages").mkdir(exist_ok=True)
            (self.output_dir / "en").mkdir(exist_ok=True)
            (self.output_dir / "en" / "pages").mkdir(exist_ok=True)
            (self.output_dir / "assets").mkdir(exist_ok=True)
        else:
            # 单语言目录结构
            (self.output_dir / "pages").mkdir(exist_ok=True)
            (self.output_dir / "assets").mkdir(exist_ok=True)
        
        # 存储处理的页面和资源
        self.processed_pages = []
        self.downloaded_assets = []
        
        if self.use_selenium:
            self._setup_selenium()
    
    def _check_output_directory(self):
        """检查输出目录是否为空，如果不为空则提示用户"""
        if not self.output_dir.exists():
            # 目录不存在，可以安全创建
            return
        
        # 检查目录是否为空（忽略隐藏文件和常见的系统文件）
        existing_files = []
        ignore_patterns = {'.DS_Store', 'Thumbs.db', '.gitkeep', '.gitignore'}
        
        try:
            for item in self.output_dir.iterdir():
                if item.name not in ignore_patterns and not item.name.startswith('.'):
                    existing_files.append(item.name)
        except PermissionError:
            logger.warning(f"⚠️ 无法访问目录 {self.output_dir}，权限不足")
            return
        
        if existing_files:
            if not self.force_overwrite:
                logger.error(f"❌ 输出目录 {self.output_dir} 不为空")
                logger.error(f"📁 发现以下文件/目录: {', '.join(existing_files[:5])}")
                if len(existing_files) > 5:
                    logger.error(f"   ... 还有 {len(existing_files) - 5} 个其他项目")
                logger.error("💡 解决方案:")
                logger.error("   1. 选择一个空目录作为输出目录")
                logger.error("   2. 手动清空当前目录")
                logger.error("   3. 使用 --force 参数强制覆盖（谨慎使用）")
                raise Exception(f"输出目录不为空: {self.output_dir}")
            else:
                logger.warning(f"⚠️ 输出目录 {self.output_dir} 不为空，启用强制覆盖模式")
                logger.warning(f"📁 发现现有文件: {', '.join(existing_files[:3])}")
                if len(existing_files) > 3:
                    logger.warning(f"   ... 等 {len(existing_files)} 个项目")
                
                # 强制模式：清空目录
                logger.info("🗑️ 正在清空输出目录...")
                self._clear_directory()
                logger.info("✅ 目录已清空")
        else:
            logger.info(f"✅ 输出目录 {self.output_dir} 为空，可以安全使用")
    
    def _clear_directory(self):
        """清空输出目录中的所有文件和子目录"""
        import shutil
        
        ignore_patterns = {'.DS_Store', 'Thumbs.db', '.gitkeep', '.gitignore'}
        
        try:
            for item in self.output_dir.iterdir():
                # 跳过隐藏文件和系统文件
                if item.name in ignore_patterns or item.name.startswith('.'):
                    continue
                
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                        logger.debug(f"🗑️ 删除目录: {item.name}")
                    else:
                        item.unlink()
                        logger.debug(f"🗑️ 删除文件: {item.name}")
                except Exception as e:
                    logger.warning(f"⚠️ 无法删除 {item.name}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 清空目录失败: {e}")
            raise Exception(f"无法清空输出目录: {e}")
    
    def _setup_selenium(self):
        """设置 Selenium WebDriver（优先使用Edge，备选Chrome），支持重试机制"""
        max_retries = 3
        retry_delay = 2  # 重试间隔秒数
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 第 {attempt + 1}/{max_retries} 次尝试启动 Selenium WebDriver...")
                
                # 首先尝试使用 Microsoft Edge
                edge_success = self._try_setup_edge(attempt + 1)
                if edge_success:
                    return
                
                # 如果Edge失败，尝试Chrome
                chrome_success = self._try_setup_chrome(attempt + 1)
                if chrome_success:
                    return
                
                # 如果这次尝试失败，但还有重试机会
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ 第 {attempt + 1} 次尝试失败，{retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # 逐渐增加重试间隔
                else:
                    # 最后一次尝试也失败了
                    logger.error("❌ 所有重试均失败，Selenium 启动失败")
                    raise Exception(f"经过 {max_retries} 次重试，仍无法启动 Selenium WebDriver")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ 第 {attempt + 1} 次尝试异常: {e}")
                    logger.info(f"🔄 {retry_delay} 秒后进行第 {attempt + 2} 次重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(f"❌ 最终尝试失败: {e}")
                    raise Exception(f"经过 {max_retries} 次重试，Selenium WebDriver 启动失败: {e}")

    def _try_setup_edge(self, attempt_num: int) -> bool:
        """尝试设置 Edge WebDriver"""
        try:
            logger.info(f"🔄 第 {attempt_num} 次尝试启动 Microsoft Edge WebDriver...")
            edge_options = EdgeOptions()
            edge_options.add_argument("--headless")
            edge_options.add_argument("--no-sandbox")
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_argument("--disable-gpu")
            edge_options.add_argument("--window-size=1920,1080")
            edge_options.add_argument("--disable-blink-features=AutomationControlled")
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_options.add_experimental_option('useAutomationExtension', False)
            # 添加更多选项来处理网络连接
            edge_options.add_argument("--disable-web-security")
            edge_options.add_argument("--allow-running-insecure-content")
            edge_options.add_argument("--disable-extensions")
            edge_options.add_argument("--disable-plugins")
            edge_options.add_argument("--disable-images")  # 加快加载速度
            edge_options.add_argument("--disable-javascript-harmony-shipping")
            edge_options.add_argument("--disable-background-timer-throttling")
            edge_options.add_argument("--disable-renderer-backgrounding")
            edge_options.add_argument("--disable-backgrounding-occluded-windows")
            edge_options.add_argument("--disable-client-side-phishing-detection")
            edge_options.add_argument("--disable-sync")
            edge_options.add_argument("--disable-translate")
            edge_options.add_argument("--hide-scrollbars")
            edge_options.add_argument("--mute-audio")
            
            try:
                # 尝试自动下载并设置 EdgeDriver
                edge_service = EdgeService(EdgeChromiumDriverManager().install())
            except Exception as download_error:
                logger.warning(f"无法下载EdgeDriver: {download_error}")
                # 尝试使用系统已安装的EdgeDriver
                try:
                    edge_service = EdgeService()  # 使用默认路径
                except:
                    raise Exception("EdgeDriver不可用，无法下载也无法在系统中找到")
            
            self.driver = webdriver.Edge(service=edge_service, options=edge_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # 设置超时
            self.driver.set_page_load_timeout(60)  # 增加页面加载超时
            self.driver.implicitly_wait(15)        # 增加隐式等待时间
            
            logger.info("🚀 Microsoft Edge WebDriver 已启动")
            return True
            
        except Exception as edge_error:
            logger.warning(f"Edge 第 {attempt_num} 次启动失败: {edge_error}")
            return False

    def _try_setup_chrome(self, attempt_num: int) -> bool:
        """尝试设置 Chrome WebDriver"""
        try:
            logger.info(f"🔄 第 {attempt_num} 次尝试启动 Chrome WebDriver...")
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-javascript-harmony-shipping")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-client-side-phishing-detection")
            chrome_options.add_argument("--disable-sync")
            chrome_options.add_argument("--disable-translate")
            chrome_options.add_argument("--hide-scrollbars")
            chrome_options.add_argument("--mute-audio")
            
            try:
                # 尝试自动下载并设置 ChromeDriver
                chrome_service = ChromeService(ChromeDriverManager().install())
            except Exception as download_error:
                logger.warning(f"无法下载ChromeDriver: {download_error}")
                # 尝试使用系统已安装的ChromeDriver
                try:
                    chrome_service = ChromeService()  # 使用默认路径
                except:
                    raise Exception("ChromeDriver不可用，无法下载也无法在系统中找到")
            
            self.driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # 设置超时
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(15)
            
            logger.info("🚀 Chrome WebDriver 已启动")
            return True
            
        except Exception as chrome_error:
            logger.warning(f"Chrome 第 {attempt_num} 次启动失败: {chrome_error}")
            return False
    
    def _get_page_content(self, url: str) -> str:
        """获取页面内容"""
        if self.use_selenium and self.driver:
            return self._get_page_with_selenium(url)
        else:
            return self._get_page_with_requests(url)
    
    def _get_page_with_selenium(self, url: str) -> str:
        """使用 Selenium 获取页面内容（等待动态加载）"""
        try:
            logger.info(f"🔄 正在加载页面（Selenium）: {url}")
            self.driver.get(url)
            
            # 等待页面基本加载
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 等待更长时间让内容加载
            logger.info("⏳ 等待JavaScript执行完成...")
            time.sleep(8)  # 增加等待时间
            
            # 尝试等待内容加载完成（检查是否还有 Loading... 文本）
            try:
                WebDriverWait(self.driver, 15).until_not(
                    EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "Loading...")
                )
                logger.info("✅ 动态内容已加载")
            except:
                logger.warning("⚠️ 页面可能仍在加载中，继续处理")
            
            # 额外等待确保所有异步内容都加载完成
            logger.info("🔍 等待异步内容加载...")
            time.sleep(5)
            
            # 尝试触发一些用户交互来确保所有内容都被渲染
            try:
                # 滚动页面以触发懒加载内容
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
                
                # 检查是否有导航菜单并尝试展开
                nav_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                    "[class*='nav'], [class*='menu'], [class*='sidebar'], [role='navigation']")
                if nav_elements:
                    logger.info(f"🔍 发现 {len(nav_elements)} 个导航元素")
                    for nav in nav_elements[:3]:  # 只处理前3个
                        try:
                            # 尝试点击可能的展开按钮
                            expandable = nav.find_elements(By.CSS_SELECTOR, 
                                "[aria-expanded='false'], .collapsed, .expand-btn")
                            for btn in expandable:
                                if btn.is_displayed():
                                    btn.click()
                                    time.sleep(1)
                        except:
                            pass
                            
            except Exception as e:
                logger.debug(f"交互操作失败: {e}")
            
            # 获取最终的页面源码
            page_source = self.driver.page_source
            logger.info(f"📄 获取页面源码: {len(page_source)} 字符")
            
            return page_source
            
        except Exception as e:
            logger.error(f"Selenium 获取页面失败: {e}")
            return self._get_page_with_requests(url)
    
    def _get_page_with_requests(self, url: str) -> str:
        """使用 requests 获取页面内容"""
        try:
            logger.info(f"📡 正在获取页面: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"获取页面失败: {e}")
            return ""
    
    def _safe_decode_unicode(self, text):
        """改进的 Unicode 解码，更好地处理转义字符"""
        try:
            # 首先处理常见的转义序列
            text = text.replace('\\n', '\n')
            text = text.replace('\\t', '\t')
            text = text.replace('\\r', '\r')
            text = text.replace('\\"', '"')
            text = text.replace('\\/', '/')
            text = text.replace('\\\\', '\\')  # 处理双反斜杠
            
            # 处理 Unicode 转义
            text = text.replace('\\u003c', '<')
            text = text.replace('\\u003e', '>')
            text = text.replace('\\u0026', '&')
            text = text.replace('\\u0027', "'")
            
            # 处理其他 Unicode 转义序列
            def replace_unicode(match):
                try:
                    return chr(int(match.group(1), 16))
                except:
                    return match.group(0)
            
            text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, text)
            
            return text
        except Exception as e:
            logger.debug(f"Unicode 解码失败: {e}")
            return text
    
    def _extract_nextjs_content(self, html_content: str, navigation_links: dict = None) -> tuple:
        """从 Next.js 的异步内容中提取页面和导航结构"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 存储页面片段
        page_fragments = {}
        navigation_structure = []
        
        # 查找所有包含内容的脚本
        scripts = soup.find_all('script')
        
        logger.info(f"🔍 分析 {len(scripts)} 个脚本标签...")
        
        for i, script in enumerate(scripts):
            if script.string and 'self.__next_f.push' in script.string:
                script_content = script.string
                
                # 提取导航结构
                nav_structure = self._extract_navigation_structure(script_content)
                if nav_structure:
                    navigation_structure.extend(nav_structure)
                
                # 提取这个脚本中的所有内容片段
                fragments = self._extract_all_content_fragments(script_content, navigation_links)
                
                for fragment in fragments:
                    title = fragment['title']
                    content = fragment['content']
                    original_filename = fragment.get('original_filename')
                    
                    if title not in page_fragments:
                        page_fragments[title] = {
                            'contents': [],
                            'original_filename': original_filename
                        }
                    
                    page_fragments[title]['contents'].append(content)
                    # 如果有原始文件名，保留第一个找到的
                    if original_filename and not page_fragments[title]['original_filename']:
                        page_fragments[title]['original_filename'] = original_filename
        
        # 合并每个页面的所有片段
        final_pages = []
        for title, page_data in page_fragments.items():
            # 合并内容
            merged_content = '\n'.join(page_data['contents'])
            
            # 清理合并后的内容
            cleaned_content = self._clean_merged_content(merged_content)
            
            if cleaned_content and len(cleaned_content) > 100:
                original_filename = page_data.get('original_filename')
                slug = self._generate_slug(title, original_filename)
                
                final_pages.append({
                    'title': title,
                    'content': cleaned_content,
                    'slug': slug,
                    'original_filename': original_filename,
                    'order': self._get_page_order_from_nav(title, navigation_structure)
                })
        
        logger.info(f"📄 提取到 {len(final_pages)} 个完整页面")
        logger.info(f"📋 提取到导航结构: {len(navigation_structure)} 个条目")
        
        return final_pages, navigation_structure
    
    def _extract_all_content_fragments(self, script_content: str, navigation_links: dict = None) -> list:
        """提取脚本中的所有内容片段，正确处理嵌套引号"""
        fragments = []
        
        # 使用更智能的方法来提取内容，正确处理嵌套引号
        pattern = r'self\.__next_f\.push\(\[1,"'
        matches = list(re.finditer(pattern, script_content))
        
        for match in matches:
            start_pos = match.end()
            
            # 从这个位置开始，找到匹配的结束引号
            content = ""
            pos = start_pos
            escape_next = False
            
            while pos < len(script_content):
                char = script_content[pos]
                
                if escape_next:
                    content += char
                    escape_next = False
                elif char == '\\':
                    content += char
                    escape_next = True
                elif char == '"':
                    # 找到结束引号
                    break
                else:
                    content += char
                
                pos += 1
            
            # 安全解码
            decoded_content = self._safe_decode_unicode(content)
            
            # 检查是否包含有效内容
            if len(decoded_content.strip()) > 20:
                # 尝试识别标题和原始文件名
                title = self._extract_title_from_content(decoded_content)
                original_filename = self._extract_original_filename(decoded_content)
                
                if title:
                    # 优先从导航链接中获取真实文件名
                    real_filename = None
                    if navigation_links and title in navigation_links:
                        real_filename = navigation_links[title]
                        logger.info(f"🎯 使用导航链接文件名: {title} -> {real_filename}")
                    else:
                        # 如果导航链接中没有，尝试从内容中提取
                        real_filename = self._extract_original_filename(decoded_content)
                        if real_filename:
                            logger.info(f"🔍 从内容提取文件名: {title} -> {real_filename}")
                        else:
                            logger.debug(f"🔍 未找到原始文件名: {title}")
                    
                    fragments.append({
                        'title': title,
                        'content': decoded_content,
                        'original_filename': real_filename
                    })
        
        return fragments
    
    def _extract_navigation_structure(self, script_content: str) -> list:
        """提取 DeepWiki 的导航结构"""
        navigation = []
        
        try:
            # 专门搜索包含路由信息的数据结构
            # 这些可能包含真实的文件名
            route_patterns = [
                # 搜索路由配置
                r'"routes?":\s*\[([^\]]+)\]',
                r'"paths?":\s*\[([^\]]+)\]',
                r'"links?":\s*\[([^\]]+)\]',
                # 搜索页面配置
                r'"pages":\s*\[([^\]]+)\]',
                r'"navigation":\s*\[([^\]]+)\]',
                r'"sidebar":\s*\[([^\]]+)\]',
                r'"menuItems":\s*\[([^\]]+)\]',
                # 搜索Next.js路由数据
                r'"__NEXT_DATA__"[^{]*{[^}]*"page"[^}]*}',
                # 搜索包含href或path的对象
                r'\{[^}]*"(?:href|path|route)":\s*"[^"]*\/([0-9]+(?:\.[0-9]+)?-[a-zA-Z][a-zA-Z0-9-]*)"[^}]*\}',
            ]
            
            logger.debug(f"🔍 在 {len(script_content)} 字符的脚本中搜索导航结构...")
            
            for pattern in route_patterns:
                matches = re.finditer(pattern, script_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    logger.debug(f"📝 找到模式匹配: {pattern[:50]}...")
                    if match.groups():
                        nav_content = match.group(1) if len(match.groups()) >= 1 else match.group(0)
                        nav_items = self._parse_navigation_items(nav_content)
                        if nav_items:
                            navigation.extend(nav_items)
                            logger.info(f"📋 从模式中提取到 {len(nav_items)} 个导航项")
            
            # 如果没有找到明确的导航结构，尝试从页面顺序推断
            if not navigation:
                logger.debug("🔍 尝试从内容推断导航结构...")
                navigation = self._infer_navigation_from_content(script_content)
                
        except Exception as e:
            logger.debug(f"提取导航结构失败: {e}")
        
        return navigation
    
    def _parse_navigation_items(self, nav_content: str) -> list:
        """解析导航项目，特别关注文件名信息"""
        items = []
        try:
            # 首先搜索包含路径信息的完整对象
            filename_objects = re.findall(
                r'\{[^}]*(?:"title":\s*"([^"]+)")[^}]*(?:"(?:href|path|route)":\s*"[^"]*\/([0-9]+(?:\.[0-9]+)?-[a-zA-Z][a-zA-Z0-9-]*)"[^}]*|[^}]*"(?:href|path|route)":\s*"[^"]*\/([0-9]+(?:\.[0-9]+)?-[a-zA-Z][a-zA-Z0-9-]*)"[^}]*"title":\s*"([^"]+)")[^}]*\}',
                nav_content,
                re.IGNORECASE
            )
            
            if filename_objects:
                logger.info(f"🎯 找到包含文件名的导航对象: {len(filename_objects)} 个")
                for match in filename_objects:
                    title = match[0] or match[3]  # title可能在不同位置
                    filename = match[1] or match[2]  # filename也可能在不同位置
                    if title and filename:
                        items.append({
                            'title': title,
                            'filename': filename,
                            'order': len(items),
                            'level': 0
                        })
                        logger.info(f"📝 导航项: {title} -> {filename}")
            
            # 如果没找到带文件名的，尝试传统的解析
            if not items:
                # 尝试解析 JSON 格式的导航项
                # 简化处理，查找标题和顺序信息
                title_pattern = r'"title":\s*"([^"]+)"'
                order_pattern = r'"order":\s*(\d+)'
                level_pattern = r'"level":\s*(\d+)'
                
                titles = re.findall(title_pattern, nav_content)
                orders = re.findall(order_pattern, nav_content)
                levels = re.findall(level_pattern, nav_content)
                
                for i, title in enumerate(titles):
                    item = {
                        'title': title,
                        'order': int(orders[i]) if i < len(orders) else i,
                        'level': int(levels[i]) if i < len(levels) else 0
                    }
                    items.append(item)
                    
        except Exception as e:
            logger.debug(f"解析导航项失败: {e}")
        
        return items
    
    def _infer_navigation_from_content(self, script_content: str) -> list:
        """从内容中推断导航结构"""
        items = []
        
        try:
            # 查找所有页面标题的出现顺序
            title_pattern = r'# ([^#\n]+)'
            matches = re.finditer(title_pattern, script_content)
            
            order = 0
            for match in matches:
                title = match.group(1).strip()
                if len(title) > 2 and not title.startswith('#'):
                    items.append({
                        'title': title,
                        'order': order,
                        'level': 0
                    })
                    order += 1
                    
        except Exception as e:
            logger.debug(f"推断导航结构失败: {e}")
        
        return items
    
    def _get_page_order_from_nav(self, page_title: str, navigation: list) -> int:
        """从导航结构中获取页面顺序"""
        for nav_item in navigation:
            if nav_item['title'] == page_title:
                return nav_item['order']
        
        # 如果没找到，返回较大的数字，排在最后
        return 9999
    
    def _extract_title_from_content(self, content: str) -> str:
        """从内容中提取标题"""
        lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('# ') and not line.startswith('# #'):
                return line.lstrip('#').strip()
        
        return None
    
    def _process_sources_links(self, content: str, github_info: dict) -> str:
        """处理 Sources 链接，补全 GitHub 地址"""
        if not github_info or not github_info.get('repo_url'):
            return content
        
        repo_url = github_info['repo_url']
        commit_sha = github_info.get('commit_sha', 'main')
        
        # 匹配 Sources 行中的链接格式：[filename:line1-line2]() 或 [filename:line1]()
        sources_pattern = r'Sources:\s*(.+?)(?=\n|$)'
        link_pattern = r'\[([^:]+):(\d+)(?:-(\d+))?\]\(\)'
        
        def replace_sources_line(match):
            sources_line = match.group(1)
            
            def replace_single_link(link_match):
                filename = link_match.group(1)
                start_line = link_match.group(2)
                end_line = link_match.group(3)  # 可能为 None
                
                # 构造 GitHub 链接
                if end_line:
                    # 有结束行号：[filename:start-end]
                    github_link = f"{repo_url}/blob/{commit_sha}/{filename}#L{start_line}-L{end_line}"
                    return f"[{filename}:{start_line}-{end_line}]({github_link})"
                else:
                    # 只有单行：[filename:line]
                    github_link = f"{repo_url}/blob/{commit_sha}/{filename}#L{start_line}"
                    return f"[{filename}:{start_line}]({github_link})"
            
            updated_line = re.sub(link_pattern, replace_single_link, sources_line)
            return f"Sources: {updated_line}"
        
        # 替换所有 Sources 行
        processed_content = re.sub(sources_pattern, replace_sources_line, content, flags=re.MULTILINE)
        
        return processed_content

    def _extract_dynamic_navigation_data(self, html_content: str) -> dict:
        """从动态加载的页面中提取真实的导航数据"""
        navigation_data = {}
        
        if not self.use_selenium or not self.driver:
            logger.debug("Selenium未启用，跳过动态导航数据提取")
            return navigation_data
        
        try:
            logger.info("🔍 分析动态导航数据...")
            
            # 1. 尝试从JavaScript执行上下文中获取路由信息
            try:
                # 检查React Router数据
                router_data = self.driver.execute_script("""
                    // 尝试获取React Router或Next.js路由数据
                    if (window.__NEXT_DATA__) {
                        return window.__NEXT_DATA__;
                    }
                    
                    // 尝试获取React状态
                    if (window.React && window.React.Component) {
                        const components = document.querySelectorAll('[data-reactroot]');
                        for (let comp of components) {
                            if (comp._reactInternalFiber || comp._reactInternalInstance) {
                                // 有React组件
                                return 'REACT_FOUND';
                            }
                        }
                    }
                    
                    // 查找可能的导航数据
                    const navElements = document.querySelectorAll('nav, [role="navigation"], .sidebar, .nav-menu');
                    const navData = [];
                    for (let nav of navElements) {
                        const links = nav.querySelectorAll('a[href]');
                        for (let link of links) {
                            const href = link.getAttribute('href');
                            const text = link.textContent.trim();
                            if (href && text && href.includes('-')) {
                                navData.push({href: href, text: text});
                            }
                        }
                    }
                    return navData.length > 0 ? navData : null;
                """)
                
                if router_data:
                    logger.info(f"🎯 获取到JavaScript路由数据: {type(router_data)}")
                    if isinstance(router_data, list):
                        # 处理导航链接数据
                        for item in router_data:
                            if isinstance(item, dict) and 'href' in item and 'text' in item:
                                href = item['href']
                                text = item['text']
                                # 提取文件名
                                filename = self._extract_filename_from_href(href)
                                if filename:
                                    navigation_data[text] = filename
                                    logger.info(f"🔗 动态导航: {text} -> {filename}")
                    elif isinstance(router_data, dict):
                        # 处理Next.js数据
                        logger.debug(f"Next.js数据结构: {list(router_data.keys())}")
                        # 可以进一步解析Next.js的路由数据
                        
            except Exception as e:
                logger.debug(f"JavaScript执行失败: {e}")
            
            # 2. 直接检查当前页面的所有链接
            try:
                links = self.driver.find_elements(By.CSS_SELECTOR, "a[href]")
                logger.info(f"🔍 分析页面中的 {len(links)} 个链接...")
                
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        text = link.text.strip()
                        
                        if href and text and len(text) > 2:
                            # 检查链接是否包含序号文件名模式
                            filename = self._extract_filename_from_href(href)
                            if filename and re.match(r'^[0-9]+(\.[0-9]+)?-[a-zA-Z]', filename):
                                navigation_data[text] = filename
                                logger.info(f"🎯 找到序号链接: {text} -> {filename}")
                                
                    except Exception as e:
                        logger.debug(f"处理链接失败: {e}")
                        
            except Exception as e:
                logger.debug(f"链接分析失败: {e}")
            
            # 3. 尝试模拟用户操作来展开更多导航
            try:
                # 查找可能的展开按钮
                expand_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                    "[aria-expanded='false'], .expand, .collapse, .toggle-btn, .menu-toggle")
                
                for btn in expand_buttons[:5]:  # 最多尝试5个按钮
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            logger.debug("🔄 尝试展开导航菜单...")
                            btn.click()
                            time.sleep(2)
                            
                            # 重新检查链接
                            new_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href]")
                            for link in new_links:
                                href = link.get_attribute('href')
                                text = link.text.strip()
                                
                                if href and text and text not in navigation_data:
                                    filename = self._extract_filename_from_href(href)
                                    if filename and re.match(r'^[0-9]+(\.[0-9]+)?-[a-zA-Z]', filename):
                                        navigation_data[text] = filename
                                        logger.info(f"🆕 展开后发现: {text} -> {filename}")
                                        
                    except Exception as e:
                        logger.debug(f"展开操作失败: {e}")
                        
            except Exception as e:
                logger.debug(f"展开导航失败: {e}")
                
        except Exception as e:
            logger.debug(f"动态导航数据提取失败: {e}")
        
        logger.info(f"🎯 动态提取到 {len(navigation_data)} 个真实文件名映射")
        return navigation_data
    
    def _extract_filename_from_href(self, href: str) -> str:
        """从href中提取文件名"""
        if not href:
            return None
            
        try:
            # 移除查询参数和锚点
            href = href.split('?')[0].split('#')[0]
            
            # 获取路径的最后一段
            path_segments = href.strip('/').split('/')
            if path_segments:
                filename = path_segments[-1]
                
                # 检查是否是有效的序号文件名
                if re.match(r'^[0-9]+(\.[0-9]+)?-[a-zA-Z][a-zA-Z0-9-]*$', filename):
                    return filename
                    
                # 也检查倒数第二段
                if len(path_segments) >= 2:
                    filename = path_segments[-2]
                    if re.match(r'^[0-9]+(\.[0-9]+)?-[a-zA-Z][a-zA-Z0-9-]*$', filename):
                        return filename
                        
        except Exception as e:
            logger.debug(f"提取文件名失败: {e}")
        
        return None
    
    def _extract_navigation_links(self, html_content: str) -> dict:
        """从页面导航栏提取真正的文件名链接"""
        title_to_filename = {}
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找所有导航链接
            # DeepWiki 的导航链接通常在左侧侧边栏
            nav_links = soup.find_all('a', href=True)
            
            logger.debug(f"🔍 分析 {len(nav_links)} 个链接...")
            
            # 调试：输出前几个链接的详细信息
            for i, link in enumerate(nav_links[:10]):  # 只看前10个
                href = link.get('href', '')
                title = link.get_text(strip=True)
                classes = link.get('class', [])
                logger.debug(f"🔗 链接 {i+1}: href='{href}', title='{title}', classes={classes}")
            
            for link in nav_links:
                href = link.get('href', '')
                title = link.get_text(strip=True)
                
                # 更灵活的链接检查
                # 检查是否包含序号文件名模式
                if href and title:
                    # 提取 href 中的最后一个路径段
                    path_segments = href.strip('/').split('/')
                    if path_segments:
                        filename = path_segments[-1]
                        
                        # 检查是否是有效的序号文件名
                        if re.match(r'^[0-9]+(\.[0-9]+)?-[a-zA-Z][a-zA-Z0-9-]*$', filename):
                            title_to_filename[title] = filename
                            logger.info(f"🔗 找到导航链接: {title} -> {filename}")
                        else:
                            # 调试：记录所有找到的链接
                            logger.debug(f"📝 检查链接: {title} -> {href} (文件名: {filename})")
            
            if not title_to_filename:
                # 如果没找到任何序号链接，尝试更宽松的搜索
                logger.debug("🔍 尝试宽松搜索...")
                for link in nav_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # 检查任何包含连字符的路径段
                    if href and title and '-' in href:
                        path_segments = href.strip('/').split('/')
                        for segment in path_segments:
                            if re.match(r'^[0-9]+.*-[a-zA-Z]', segment):
                                title_to_filename[title] = segment
                                logger.info(f"🔗 宽松匹配导航链接: {title} -> {segment}")
                                break
            
            logger.info(f"📋 从导航栏提取到 {len(title_to_filename)} 个文件名映射")
            return title_to_filename
            
        except Exception as e:
            logger.error(f"提取导航链接失败: {e}")
            return {}
    
    def _extract_original_filename(self, content: str) -> str:
        """从内容中提取原始文件名"""
        try:
            # 首先进行广泛搜索，看看内容中有什么数字-连字符模式
            broad_search = re.findall(r'\b[0-9]+[-\.][a-zA-Z][a-zA-Z0-9-]*\b', content)
            if broad_search:
                logger.debug(f"🔍 广泛搜索找到的模式: {broad_search[:10]}")  # 只显示前10个
            
            # 1. 首先搜索标准的序号文件名模式（如 "1-overview", "4.1-backend-api-reference"）
            standard_patterns = [
                # 匹配 "1-overview", "2-getting-started" 等模式
                r'"([0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)"',
                r"'([0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)'",
                # 匹配 "1.1-system-architecture", "4.1-backend-api-reference" 等模式
                r'"([0-9]{1,2}\.[0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)"',
                r"'([0-9]{1,2}\.[0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)'",
                # 匹配路径中的文件名
                r'\/([0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)(?:\/|"|\?|$)',
                r'\/([0-9]{1,2}\.[0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)(?:\/|"|\?|$)',
                # 不用引号包围的模式
                r'\b([0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)\b',
                r'\b([0-9]{1,2}\.[0-9]{1,2}-[a-zA-Z][a-zA-Z0-9-]*)\b',
            ]
            
            # 收集所有匹配的标准文件名
            found_standard_names = []
            for pattern in standard_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if len(match) >= 5:  # 至少像 "1-abc" 这样的长度
                        found_standard_names.append(match)
                        logger.debug(f"🎯 找到标准序号文件名: {match}")
            
            # 如果找到标准格式的文件名，返回最合适的
            if found_standard_names:
                # 按长度和复杂度排序，选择最合理的
                best_name = min(found_standard_names, key=lambda x: (len(x), x))
                logger.debug(f"✅ 选择最佳标准文件名: {best_name}")
                return best_name
            
            # 2. 如果没找到标准格式，搜索可能的路由或slug信息
            route_patterns = [
                # 在Next.js路由数据中搜索
                r'"pathname":\s*"[^"]*\/([^"\/]+)"',
                r'"href":\s*"[^"]*\/([^"\/]+)"',
                r'"slug":\s*"([^"]+)"',
                # 在React组件props中搜索
                r'"params":\s*{[^}]*"slug":\s*"([^"]*)"',
                r'"query":\s*{[^}]*"slug":\s*"([^"]*)"',
                # 在页面元数据中搜索
                r'"page":\s*{[^}]*"slug":\s*"([^"]*)"',
                r'"route":\s*"[^"]*\/([^"\/]+)"',
            ]
            
            route_candidates = []
            for pattern in route_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if match and len(match) > 2 and not match.isdigit():
                        # 检查是否可能是文件名
                        if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-_.]*$', match):
                            route_candidates.append(match)
                            logger.debug(f"📝 发现路由候选: {match}")
            
            # 3. 特别搜索可能被编码的文件名
            encoded_patterns = [
                # 搜索被HTML编码的内容
                r'&quot;([0-9]{1,2}[-\.][a-zA-Z][a-zA-Z0-9-]*)&quot;',
                # 搜索被转义的JSON字符串
                r'\\"([0-9]{1,2}[-\.][a-zA-Z][a-zA-Z0-9-]*)\\"',
                # 搜索URL编码的内容
                r'%22([0-9]{1,2}[-\.][a-zA-Z][a-zA-Z0-9-]*)%22',
            ]
            
            for pattern in encoded_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if len(match) >= 5:
                        logger.debug(f"🔓 找到编码的文件名: {match}")
                        return match
            
            # 4. 如果还是没找到，返回最佳的路由候选
            if route_candidates:
                # 优先选择包含连字符的（更可能是文件名）
                dash_candidates = [c for c in route_candidates if '-' in c]
                if dash_candidates:
                    best_candidate = min(dash_candidates, key=len)
                    logger.debug(f"🔄 选择连字符候选: {best_candidate}")
                    return best_candidate
                else:
                    best_candidate = min(route_candidates, key=len)
                    logger.debug(f"🔄 选择路由候选: {best_candidate}")
                    return best_candidate
                
        except Exception as e:
            logger.debug(f"提取原始文件名失败: {e}")
        
        return None
    
    def _sort_pages_by_order(self, pages: list) -> list:
        """按照序号和标题对页面进行排序"""
        def get_sort_key(page):
            slug = page.get('slug', '')
            title = page.get('title', '')
            
            # 尝试从 slug 中提取序号
            slug_match = re.match(r'^(\d+)', slug)
            if slug_match:
                return (int(slug_match.group(1)), slug)
            
            # 尝试从标题中提取序号
            title_match = re.match(r'^(\d+)', title)
            if title_match:
                return (int(title_match.group(1)), title)
            
            # 使用 order 属性（如果有的话）
            order = page.get('order', 9999)
            if order != 9999:
                return (order, title)
            
            # 默认按标题排序，但放在最后
            return (9999, title)
        
        return sorted(pages, key=get_sort_key)
    
    def _clean_merged_content(self, content: str) -> str:
        """清理合并后的内容"""
        # 移除重复的标题
        lines = content.split('\n')
        cleaned_lines = []
        seen_title = None
        
        for line in lines:
            line_stripped = line.strip()
            
            # 如果是标题行
            if line_stripped.startswith('# ') and not line_stripped.startswith('# #'):
                title = line_stripped.lstrip('#').strip()
                if seen_title is None:
                    seen_title = title
                    cleaned_lines.append(line)
                elif title == seen_title:
                    # 跳过重复的标题
                    continue
                else:
                    # 新的标题，可能是子章节
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
        
        # 移除明显的数据行
        final_lines = []
        in_code_block = False
        
        for line in cleaned_lines:
            line_stripped = line.strip()
            
            # 处理代码块
            if line_stripped.startswith('```'):
                in_code_block = not in_code_block
                final_lines.append(line)
                continue
            
            # 在代码块内，保留所有内容
            if in_code_block:
                final_lines.append(line)
                continue
            
            # 跳过明显的数据行，但保留其他内容
            if (line_stripped.startswith('{"') or 
                line_stripped.startswith('["') or
                ('"ID":' in line_stripped and '"' in line_stripped) or
                (line_stripped.count('"') > 6 and ':' in line_stripped)):
                continue
            
            final_lines.append(line)
        
        return '\n'.join(final_lines).strip()
    
    def _generate_slug(self, title: str, original_filename: str = None) -> str:
        """生成页面的 slug，优先使用正确的原始文件名"""
        
        # 如果有正确的原始文件名，直接使用
        if original_filename:
            logger.debug(f"✅ 使用原始文件名: {title} -> {original_filename}")
            return original_filename
        
        # 如果没有映射的文件名，检查标题是否以序号开头
        title_with_number = re.match(r'^(\d+)[\.\s-]*(.+)', title)
        if title_with_number:
            number = title_with_number.group(1)
            clean_title = title_with_number.group(2)
            # 生成带序号的 slug
            slug = re.sub(r'[^\w\s-]', '', clean_title.lower())
            slug = re.sub(r'[\s_-]+', '-', slug)
            slug = slug.strip('-')
            final_slug = f"{number}-{slug}" if slug else number
            logger.debug(f"🔢 从标题提取序号: {title} -> {final_slug}")
            return final_slug
        
        # 默认处理：转换为小写，替换空格和特殊字符
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[\s_-]+', '-', slug)
        final_slug = slug.strip('-')
        logger.debug(f"📝 生成标准slug: {title} -> {final_slug}")
        return final_slug
    
    def _extract_page_info(self, html_content: str, url: str) -> dict:
        """从页面提取信息"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 提取页面标题
        title = "DeepWiki 文档"
        
        # 尝试多种方式获取标题
        title_candidates = [
            soup.find('title'),
            soup.find('h1'),
            soup.find('h2'),
            soup.select_one('[data-testid="page-title"]'),
            soup.select_one('.page-title'),
            soup.select_one('.title')
        ]
        
        for candidate in title_candidates:
            if candidate and candidate.get_text().strip():
                title = candidate.get_text().strip()
                # 清理标题
                title = re.sub(r'\s+', ' ', title)
                title = title.replace(' | DeepWiki', '')
                break
        
        # 从 URL 提取项目信息
        parsed_url = urlparse(url)
        path_parts = [part for part in parsed_url.path.strip('/').split('/') if part]
        
        project_name = ""
        if path_parts:
            if len(path_parts) >= 2:
                project_name = f"{path_parts[0]}/{path_parts[1]}"
            else:
                project_name = path_parts[0]
        
        return {
            'title': title,
            'project_name': project_name,
            'url': url,
            'path_parts': path_parts,
            'github_info': self._extract_github_info(html_content, project_name)
        }
    
    def _extract_github_info(self, html_content: str, project_name: str) -> dict:
        """从页面中提取 GitHub 仓库和 commit 信息"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        github_repo = ""
        commit_sha = ""
        
        # 查找 GitHub 链接的多种方式
        github_patterns = [
            # 直接查找 GitHub 链接
            r'https://github\.com/([^/]+/[^/\s"\'<>]+)',
            # 从脚本中查找
            r'github\.com/([^/]+/[^/\s"\'<>]+)',
            # 从源码链接中查找
            r'source.*?github\.com/([^/]+/[^/\s"\'<>]+)',
        ]
        
        # 在页面文本中搜索仓库
        for pattern in github_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    # 清理匹配结果
                    repo = match.strip().rstrip('/')
                    if '/' in repo and not repo.endswith('.git'):
                        github_repo = f"https://github.com/{repo}"
                        logger.info(f"🔗 发现 GitHub 仓库: {github_repo}")
                        break
                if github_repo:
                    break
        
        # 如果没有找到，尝试从 project_name 构造
        if not github_repo and project_name and '/' in project_name:
            github_repo = f"https://github.com/{project_name}"
            logger.info(f"📝 推测 GitHub 仓库: {github_repo}")
        
        # 查找 commit SHA
        commit_patterns = [
            # 查找 commit hash 模式（7-40字符的十六进制）
            r'commit[/_:\s]+([a-f0-9]{7,40})',
            r'sha[/_:\s]+([a-f0-9]{7,40})',
            r'revision[/_:\s]+([a-f0-9]{7,40})',
            # 查找 blob 链接中的 commit
            r'github\.com/[^/]+/[^/]+/blob/([a-f0-9]{7,40})',
            # 在脚本数据中查找
            r'"commit"[^"]*"([a-f0-9]{7,40})"',
            r'"sha"[^"]*"([a-f0-9]{7,40})"',
            # 在 meta 标签中查找
            r'<meta[^>]*content="[^"]*([a-f0-9]{7,40})[^"]*"',
        ]
        
        for pattern in commit_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                # 过滤出合法的 commit SHA（至少7位，最多40位）
                for match in matches:
                    if 7 <= len(match) <= 40:
                        commit_sha = match[:8]  # 使用前8位
                        logger.info(f"🎯 发现 commit SHA: {commit_sha}")
                        break
                if commit_sha:
                    break
        
        if not commit_sha:
            logger.warning("⚠️ 未找到 commit SHA，将使用 main 分支")
            commit_sha = "main"
        
        if not github_repo:
            logger.warning("⚠️ 未找到 GitHub 仓库信息")
        
        return {
            'repo_url': github_repo,
            'commit_sha': commit_sha
        }
    
    def convert(self) -> dict:
        """执行转换"""
        logger.info(f"🚀 开始转换 DeepWiki 站点: {self.base_url}")
        
        try:
            # 获取主页内容
            html_content = self._get_page_content(self.base_url)
            if not html_content:
                raise Exception("无法获取页面内容")
            
            # 提取基本页面信息
            main_page_info = self._extract_page_info(html_content, self.base_url)
            
            # 如果使用Selenium，尝试提取动态导航数据
            dynamic_navigation = {}
            if self.use_selenium and self.driver:
                logger.info("🎯 提取动态导航数据...")
                dynamic_navigation = self._extract_dynamic_navigation_data(html_content)
            
            # 从导航栏提取真实的文件名映射
            logger.info("🔗 分析导航栏链接...")
            navigation_links = self._extract_navigation_links(html_content)
            
            # 合并动态和静态导航数据
            if dynamic_navigation:
                logger.info(f"🔄 合并 {len(dynamic_navigation)} 个动态导航项...")
                navigation_links.update(dynamic_navigation)
            
            # 提取所有页面内容
            logger.info("🔍 提取页面内容...")
            pages, navigation_structure = self._extract_nextjs_content(html_content, navigation_links)
            
            if pages:
                logger.info(f"📋 发现 {len(pages)} 个页面")
                for page in pages:
                    logger.info(f"  - {page['title']}")
            else:
                logger.warning("未发现其他页面，将创建默认页面")
                # 如果没有找到页面，创建默认页面
                pages = [{
                    'title': main_page_info['project_name'],
                    'content': f"# {main_page_info['project_name']}\n\n> 这是默认页面内容",
                    'slug': 'home'
                }]
            
            # 对页面进行排序
            pages = self._sort_pages_by_order(pages)
            
            # 创建页面文件
            self._create_page_files(pages, main_page_info)
            
            # 生成 Docsify 配置文件
            self._generate_docsify_files(main_page_info, pages, navigation_structure)
            
            return {
                'success': True,
                'pages_processed': len(pages),
                'assets_downloaded': len(self.downloaded_assets),
                'output_dir': str(self.output_dir.absolute()),
                'main_page': main_page_info,
                'pages': pages
            }
            
        except Exception as e:
            logger.error(f"转换失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🛑 Selenium WebDriver 已关闭")
    
    def _create_page_files(self, pages: list, main_page_info: dict):
        """创建页面文件"""
        
        # 获取项目路径信息
        path_parts = main_page_info['path_parts']
        
        # 保存路径信息供其他方法使用
        self.processed_path_parts = path_parts
        
        if self.multilingual:
            # 多语言版本：为每种语言创建文件
            for lang_code in ['zh-cn', 'en']:
                if path_parts and len(path_parts) >= 2:
                    base_dir = self.output_dir / lang_code / "pages" / path_parts[0] / path_parts[1]
                else:
                    base_dir = self.output_dir / lang_code / "pages"
                
                base_dir.mkdir(parents=True, exist_ok=True)
                
                # 创建每个页面文件
                for page in pages:
                    filename = f"{page['slug']}.md"
                    file_path = base_dir / filename
                    
                    # 处理 Sources 链接
                    processed_content = self._process_sources_links(page['content'], main_page_info.get('github_info', {}))
                    
                    # 写入页面内容
                    file_path.write_text(processed_content, encoding='utf-8')
                    logger.info(f"📄 创建页面: {page['title']} -> {file_path.relative_to(self.output_dir)}")
        else:
            # 单语言版本
            # 创建页面目录
            if path_parts and len(path_parts) >= 2:
                base_dir = self.output_dir / "pages" / path_parts[0] / path_parts[1]
            else:
                base_dir = self.output_dir / "pages"
            
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建每个页面文件
            created_files = {}  # 用于跟踪已创建的文件名
            for page in pages:
                base_slug = page['slug']
                slug = base_slug
                counter = 1
                
                # 确保文件名唯一性
                while slug in created_files:
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                
                filename = f"{slug}.md"
                file_path = base_dir / filename
                created_files[slug] = True
                
                # 更新页面的 slug（用于侧边栏生成）
                page['slug'] = slug
            
                # 处理 Sources 链接
                processed_content = self._process_sources_links(page['content'], main_page_info.get('github_info', {}))
                
                # 写入页面内容
                file_path.write_text(processed_content, encoding='utf-8')
                
                # 记录处理的页面
                relative_path = str(file_path.relative_to(self.output_dir))
                self.processed_pages.append({
                    'file': relative_path,
                    'title': page['title'],
                    'slug': page['slug']
                })
                
                logger.info(f"📄 创建页面: {page['title']} -> {relative_path}")
    
    def _generate_docsify_files(self, main_page_info: dict, pages: list = None, navigation_structure: list = None):
        """生成 Docsify 配置文件"""
        
        if self.multilingual:
            # 多语言版本
            self._generate_multilingual_files(main_page_info, pages or [], navigation_structure)
        else:
            # 单语言版本
            # 生成侧边栏
            self._generate_sidebar_with_pages(pages or [], navigation_structure)
            
            # 生成 index.html
            self._generate_index_html(main_page_info['project_name'])
            
            # 生成主 README.md
            self._generate_main_readme_with_pages(main_page_info, pages or [])
        
        # 生成 .nojekyll 文件
        (self.output_dir / ".nojekyll").write_text("", encoding='utf-8')
    
    def _generate_multilingual_files(self, main_page_info: dict, pages: list, navigation_structure: list = None):
        """生成多语言版本的配置文件"""
        project_name = main_page_info['project_name']
        
        # 1. 生成根目录的 index.html（多语言版本）
        self._generate_multilingual_index_html(project_name)
        
        # 2. 生成根目录的侧边栏（语言选择）
        self._generate_root_sidebar()
        
        # 3. 生成根目录的 README.md
        self._generate_language_selection_readme(main_page_info)
        
        # 4. 生成中文版本
        self._generate_language_version('zh-cn', main_page_info, pages, '中文', navigation_structure)
        
        # 5. 生成英文版本
        self._generate_language_version('en', main_page_info, pages, 'English', navigation_structure)
        
        logger.info("🌐 多语言文件生成完成")
    
    def _generate_multilingual_index_html(self, site_name: str):
        """生成多语言版本的 index.html"""
        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{site_name}</title>
  <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1" />
  <meta name="description" content="从 DeepWiki 转换的文档站点">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, minimum-scale=1.0">
  <link rel="stylesheet" href="//unpkg.com/docsify@4/lib/themes/vue.css">
  <style>
    .sidebar {{
      padding-top: 6px;
    }}
    .markdown-section {{
      max-width: 800px;
    }}
    .app-name-link {{
      color: var(--theme-color, #42b983) !important;
    }}
    /* 语言切换按钮样式 */
    .language-switch {{
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 1000;
      background: var(--theme-color, #42b983);
      color: white;
      border: none;
      border-radius: 4px;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 14px;
      text-decoration: none;
      transition: background-color 0.3s;
    }}
    .language-switch:hover {{
      background: var(--theme-color-dark, #369870);
      color: white;
    }}
    .language-menu {{
      position: fixed;
      top: 60px;
      right: 20px;
      z-index: 1000;
      background: white;
      border: 1px solid #eee;
      border-radius: 4px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      display: none;
      min-width: 120px;
    }}
    .language-menu a {{
      display: block;
      padding: 10px 15px;
      color: #333;
      text-decoration: none;
      border-bottom: 1px solid #eee;
    }}
    .language-menu a:last-child {{
      border-bottom: none;
    }}
    .language-menu a:hover {{
      background: #f8f9fa;
    }}
    .language-menu.show {{
      display: block;
    }}
  </style>
</head>
<body>
  <div id="app">正在加载...</div>
  
  <!-- 语言切换菜单 -->
  <button class="language-switch" onclick="toggleLanguageMenu()">
    🌐 语言 / Language
  </button>
  <div class="language-menu" id="languageMenu">
    <a href="#/zh-cn/">🇨🇳 中文</a>
    <a href="#/en/">🇺🇸 English</a>
  </div>

  <script>
    // 语言切换功能
    function toggleLanguageMenu() {{
      const menu = document.getElementById('languageMenu');
      menu.classList.toggle('show');
    }}
    
    // 点击页面其他地方关闭菜单
    document.addEventListener('click', function(event) {{
      const menu = document.getElementById('languageMenu');
      const button = document.querySelector('.language-switch');
      if (!menu.contains(event.target) && !button.contains(event.target)) {{
        menu.classList.remove('show');
      }}
    }});

    window.$docsify = {{
      name: '{site_name}',
      repo: '',
      homepage: 'zh-cn/README.md',
      loadSidebar: '_sidebar.md',
      autoHeader: true,
      subMaxLevel: 3,
      maxLevel: 4,
      alias: {{
        '.*zh-cn.*/_sidebar.md': '/zh-cn/_sidebar.md',
        '.*en.*/_sidebar.md': '/en/_sidebar.md',
        '/zh-cn/README.md': '/zh-cn/README.md',
        '/en/README.md': '/en/README.md',
        '/zh-cn/pages/(.*)': '/zh-cn/pages/$1',
        '/en/pages/(.*)': '/en/pages/$1'
      }},
      fallbackLanguages: ['zh-cn'],
      nameLink: {{
        '/zh-cn/': '#/zh-cn/',
        '/en/': '#/en/',
        '/': '#/'
      }},
      search: {{
        maxAge: 86400000,
        paths: 'auto',
        placeholder: {{
          '/zh-cn/': '搜索文档...',
          '/en/': 'Search...',
          '/': '搜索文档...'
        }},
        noData: {{
          '/zh-cn/': '没有找到结果',
          '/en/': 'No results found',
          '/': '没有找到结果'
        }},
        depth: 6
      }},
      copyCode: {{
        buttonText: {{
          '/zh-cn/': '复制代码',
          '/en/': 'Copy Code',
          '/': '复制代码'
        }},
        errorText: {{
          '/zh-cn/': '复制失败',
          '/en/': 'Copy failed',
          '/': '复制失败'
        }},
        successText: {{
          '/zh-cn/': '已复制到剪贴板',
          '/en/': 'Copied to clipboard',
          '/': '已复制到剪贴板'
        }}
      }},
      pagination: {{
        previousText: {{
          '/zh-cn/': '上一页',
          '/en/': 'Previous',
          '/': '上一页'
        }},
        nextText: {{
          '/zh-cn/': '下一页',
          '/en/': 'Next',
          '/': '下一页'
        }},
        crossChapter: true,
        crossChapterText: true
      }},
      mermaid: {{
        theme: 'default'
      }}
    }}
  </script>
  <!-- Docsify v4 -->
  <script src="//unpkg.com/docsify@4"></script>
  <!-- Mermaid -->
  <script src="//unpkg.com/mermaid@9/dist/mermaid.min.js"></script>
  <script>
    mermaid.initialize({{
      theme: 'default',
      startOnLoad: false
    }});
  </script>
  <script src="//unpkg.com/docsify-mermaid@1/dist/docsify-mermaid.js"></script>
  <!-- 插件 -->
  <script src="//unpkg.com/docsify/lib/plugins/search.min.js"></script>
  <script src="//unpkg.com/docsify/lib/plugins/zoom-image.min.js"></script>
  <script src="//unpkg.com/docsify-copy-code@2"></script>
  <script src="//unpkg.com/docsify-pagination@2/dist/docsify-pagination.min.js"></script>
</body>
</html>'''
        
        index_file = self.output_dir / "index.html"
        index_file.write_text(html_content, encoding='utf-8')
        logger.info("🌐 生成多语言 index.html...")
    
    def _generate_root_sidebar(self):
        """生成根目录的侧边栏（语言选择）"""
        sidebar_content = '''<!-- 多语言文档导航 -->

* [🇨🇳 中文文档](zh-cn/)
* [🇺🇸 English Docs](en/)
'''
        
        sidebar_file = self.output_dir / "_sidebar.md"
        sidebar_file.write_text(sidebar_content, encoding='utf-8')
        logger.info("📋 生成根目录侧边栏...")
    
    def _generate_language_selection_readme(self, main_page_info: dict):
        """生成语言选择页面"""
        github_repo_link = ""
        if main_page_info.get('github_info', {}).get('repo_url'):
            github_repo_link = f"""
- **源码仓库 / Source Repository**: [{main_page_info['github_info']['repo_url']}]({main_page_info['github_info']['repo_url']})"""

        readme_content = f'''# {main_page_info['project_name']}

> 🌐 多语言文档站点 / Multilingual Documentation Site

## 语言选择 / Language Selection

请选择您的语言 / Please select your language:

### [🇨🇳 中文文档](zh-cn/)
- 完整的中文文档
- 中文界面和搜索
- 中文导航菜单

### [🇺🇸 English Documentation](en/)
- Complete English documentation  
- English interface and search
- English navigation menu

---

## 项目信息 / Project Information

- **项目名称 / Project Name**: {main_page_info['project_name']}
- **原始页面 / Original Page**: [{main_page_info['url']}]({main_page_info['url']}){github_repo_link}
- **生成时间 / Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}

## 技术支持 / Technical Support

此文档站点使用 [Docsify](https://docsify.js.org/) 构建 / This documentation site is built with [Docsify](https://docsify.js.org/)

---

*由 DeepWiki2Docsify 工具自动生成 / Automatically generated by DeepWiki2Docsify tool*
'''
        
        readme_file = self.output_dir / "README.md"
        readme_file.write_text(readme_content, encoding='utf-8')
        logger.info("📄 生成语言选择页面...")
    
    def _generate_language_version(self, lang_code: str, main_page_info: dict, pages: list, lang_name: str, navigation_structure: list = None):
        """生成特定语言版本的配置文件"""
        lang_dir = self.output_dir / lang_code
        
        # 生成该语言的侧边栏
        self._generate_language_sidebar(lang_dir, pages, lang_code, navigation_structure)
        
        # 生成该语言的 README.md
        self._generate_language_readme(lang_dir, main_page_info, pages, lang_code, lang_name)
        
        logger.info(f"📁 生成 {lang_name} 版本配置...")
    
    def _generate_language_sidebar(self, lang_dir: Path, pages: list, lang_code: str, navigation_structure: list = None):
        """生成特定语言的侧边栏"""
        if lang_code == 'zh-cn':
            sidebar_content = "<!-- 中文文档导航 -->\n\n* [首页](zh-cn/README.md)\n\n"
        else:  # en
            sidebar_content = "<!-- English Documentation Navigation -->\n\n* [Home](en/README.md)\n\n"
        
        if pages:
            # 动态生成页面路径（根据实际创建的目录结构）
            # 从第一个页面的处理信息中获取路径结构
            path_parts = []
            if hasattr(self, 'processed_path_parts'):
                path_parts = self.processed_path_parts
            
            # 构建路径前缀
            if path_parts and len(path_parts) >= 2:
                path_prefix = f"{lang_code}/pages/{path_parts[0]}/{path_parts[1]}"
            else:
                path_prefix = f"{lang_code}/pages"
            
            # 简单按字母顺序列出所有页面
            # 使用专门的多语言层级化组织方法
            organized_pages = self._organize_pages_hierarchically_for_multilingual(pages, path_prefix)
            sidebar_content += self._generate_hierarchical_sidebar_content_for_multilingual(organized_pages)
        
        sidebar_file = lang_dir / "_sidebar.md"
        sidebar_file.write_text(sidebar_content, encoding='utf-8')
    
    def _organize_pages_hierarchically_for_multilingual(self, pages: list, path_prefix: str) -> dict:
        """为多语言模式按照文件名序号组织页面层级结构"""
        organized = {}
        
        for page in pages:
            title = page['title']
            slug = page['slug']
            relative_path = f"{path_prefix}/{slug}.md"
            
            # 解析文件名序号
            sequence_info = self._parse_filename_sequence(slug)
            if sequence_info:
                major = sequence_info['major']
                minor = sequence_info.get('minor')
                
                # 确保主要分组存在
                if major not in organized:
                    organized[major] = {
                        'main_page': None,
                        'sub_pages': {},
                        'order': major
                    }
                
                if minor is None:
                    # 主页面（如 1-overview, 2-getting-started）
                    organized[major]['main_page'] = {
                        'title': title,
                        'path': relative_path,
                        'slug': slug,
                        'order': major
                    }
                else:
                    # 子页面（如 1.1-system-architecture, 2.1-installation）
                    organized[major]['sub_pages'][minor] = {
                        'title': title,
                        'path': relative_path,
                        'slug': slug,
                        'order': minor
                    }
            else:
                # 没有序号的页面放在最后
                if 999 not in organized:
                    organized[999] = {
                        'main_page': None,
                        'sub_pages': {},
                        'order': 999
                    }
                
                # 使用一个递增的序号放在子页面中
                next_order = len(organized[999]['sub_pages']) + 1
                organized[999]['sub_pages'][next_order] = {
                    'title': title,
                    'path': relative_path,
                    'slug': slug,
                    'order': next_order
                }
        
        return organized
    
    def _generate_hierarchical_sidebar_content_for_multilingual(self, organized_pages: dict) -> str:
        """为多语言模式生成层级化的侧边栏内容"""
        content = ""
        
        # 按主要序号排序
        for major in sorted(organized_pages.keys()):
            group = organized_pages[major]
            
            # 如果是最后的未分类组，添加标题
            if major == 999:
                content += "* 📋 其他页面\n"
            
            # 添加主页面
            if group['main_page']:
                main_page = group['main_page']
                content += f"* [{main_page['title']}]({main_page['path']})\n"
                
                # 添加该组的子页面
                if group['sub_pages']:
                    for minor in sorted(group['sub_pages'].keys()):
                        sub_page = group['sub_pages'][minor]
                        content += f"  * [{sub_page['title']}]({sub_page['path']})\n"
            else:
                # 如果没有主页面，但有子页面，直接列出子页面
                if group['sub_pages']:
                    if major != 999:  # 对于有序号但没有主页面的情况
                        content += f"* 📁 第 {major} 部分\n"
                    
                    for minor in sorted(group['sub_pages'].keys()):
                        sub_page = group['sub_pages'][minor]
                        indent = "  " if major != 999 else "  "
                        content += f"{indent}* [{sub_page['title']}]({sub_page['path']})\n"
            
            # 在每个主要分组后添加空行（除了最后一个）
            if major != max(organized_pages.keys()):
                content += "\n"
        
        return content
    
    def _generate_hierarchical_sidebar(self, pages: list, navigation: list, path_prefix: str, lang_code: str) -> str:
        """生成层级化的侧边栏"""
        sidebar_content = ""
        
        # 创建页面映射
        page_map = {page['title']: page for page in pages}
        
        # 按导航结构的顺序和层级生成侧边栏
        nav_sorted = sorted(navigation, key=lambda x: (x.get('order', 0), x.get('level', 0)))
        
        for nav_item in nav_sorted:
            title = nav_item['title']
            level = nav_item.get('level', 0)
            
            if title in page_map:
                page = page_map[title]
                relative_path = f"{path_prefix}/{page['slug']}.md"
                
                # 根据层级添加适当的缩进
                if level == 0:
                    sidebar_content += f"* [{title}]({relative_path})\n"
                else:
                    indent = "  " * (level + 1)
                    sidebar_content += f"{indent}* [{title}]({relative_path})\n"
        
        # 添加未在导航中的页面
        if navigation:
            nav_titles = {nav['title'] for nav in navigation}
            unmapped_pages = [page for page in pages if page['title'] not in nav_titles]
            
            if unmapped_pages:
                other_label = "* 其他页面\n" if lang_code == 'zh-cn' else "* Other Pages\n"
                sidebar_content += other_label
                for page in sorted(unmapped_pages, key=lambda p: p['title']):
                    relative_path = f"{path_prefix}/{page['slug']}.md"
                    sidebar_content += f"  * [{page['title']}]({relative_path})\n"
        
        return sidebar_content
    
    def _generate_language_readme(self, lang_dir: Path, main_page_info: dict, pages: list, lang_code: str, lang_name: str):
        """生成特定语言的 README.md"""
        
        # 构建源码仓库链接
        github_repo_link = ""
        if main_page_info.get('github_info', {}).get('repo_url'):
            repo_url = main_page_info['github_info']['repo_url']
            if lang_code == 'zh-cn':
                github_repo_link = f"\n- **源码仓库**: [{repo_url}]({repo_url})"
            else:
                github_repo_link = f"\n- **Source Repository**: [{repo_url}]({repo_url})"
        
        if lang_code == 'zh-cn':
            readme_content = f'''# {main_page_info['project_name']}

> 🚀 从 DeepWiki 转换的文档站点

## 📖 文档导航

本文档包含 **{len(pages)}** 个页面，涵盖了项目的完整技术文档。

### 文档页面

请查看左侧导航栏浏览所有页面，或使用搜索功能快速找到所需内容。

## 🔗 快速链接

- **原始页面**: [{main_page_info['url']}]({main_page_info['url']}){github_repo_link}

## 📝 使用说明

此文档站点支持：

- 📱 响应式设计，支持移动端
- 🔍 全文搜索功能
- 🖼️ 图片缩放查看
- 📋 代码一键复制
- 📄 分页导航
- 🌐 中英文切换

---

*生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*
'''
        else:  # en
            readme_content = f'''# {main_page_info['project_name']}

> 🚀 Documentation Site Converted from DeepWiki

## 📖 Documentation Navigation

This documentation contains **{len(pages)}** pages covering the complete technical documentation of the project.

### Documentation Pages

Please browse all pages using the sidebar navigation or use the search function to quickly find the content you need.

## 🔗 Quick Links

- **Original Page**: [{main_page_info['url']}]({main_page_info['url']}){github_repo_link}

## 📝 Features

This documentation site supports:

- 📱 Responsive design for mobile devices
- 🔍 Full-text search functionality
- 🖼️ Image zoom viewing
- 📋 One-click code copying
- 📄 Page navigation
- 🌐 Chinese/English switching

---

*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*
'''
        
        readme_file = lang_dir / "README.md"
        readme_file.write_text(readme_content, encoding='utf-8')
    
    def _generate_sidebar_with_pages(self, pages: list, navigation_structure: list = None):
        """生成包含所有页面的层级化侧边栏"""
        sidebar_content = "<!-- docs/_sidebar.md -->\n\n"
        sidebar_content += "* [首页](README.md)\n\n"
        
        if pages:
            # 按文件名序号进行层级排序和分组
            organized_pages = self._organize_pages_hierarchically(pages)
            sidebar_content += self._generate_hierarchical_sidebar_content(organized_pages)
        
        sidebar_file = self.output_dir / "_sidebar.md"
        sidebar_file.write_text(sidebar_content, encoding='utf-8')
        logger.info("� 生成层级化侧边栏...")
    
    def _organize_pages_hierarchically(self, pages: list) -> dict:
        """按照文件名序号组织页面层级结构"""
        organized = {}
        
        for page in pages:
            # 找到这个页面对应的处理记录
            processed_page = None
            for p in self.processed_pages:
                if p['slug'] == page['slug']:
                    processed_page = p
                    break
            
            if not processed_page:
                continue
            
            relative_path = processed_page['file']
            title = page['title']
            slug = page['slug']
            
            # 解析文件名序号
            sequence_info = self._parse_filename_sequence(slug)
            if sequence_info:
                major = sequence_info['major']
                minor = sequence_info.get('minor')
                
                # 确保主要分组存在
                if major not in organized:
                    organized[major] = {
                        'main_page': None,
                        'sub_pages': {},
                        'order': major
                    }
                
                if minor is None:
                    # 主页面（如 1-overview, 2-getting-started）
                    organized[major]['main_page'] = {
                        'title': title,
                        'path': relative_path,
                        'slug': slug,
                        'order': major
                    }
                else:
                    # 子页面（如 1.1-system-architecture, 2.1-installation）
                    organized[major]['sub_pages'][minor] = {
                        'title': title,
                        'path': relative_path,
                        'slug': slug,
                        'order': minor
                    }
            else:
                # 没有序号的页面放在最后
                if 999 not in organized:
                    organized[999] = {
                        'main_page': None,
                        'sub_pages': {},
                        'order': 999
                    }
                
                # 使用一个递增的序号放在子页面中
                next_order = len(organized[999]['sub_pages']) + 1
                organized[999]['sub_pages'][next_order] = {
                    'title': title,
                    'path': relative_path,
                    'slug': slug,
                    'order': next_order
                }
        
        return organized
    
    def _parse_filename_sequence(self, filename: str) -> dict:
        """解析文件名中的序号信息"""
        # 匹配 "1-overview", "1.1-system-architecture" 等格式
        pattern = r'^(\d+)(?:\.(\d+))?-'
        match = re.match(pattern, filename)
        
        if match:
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) else None
            return {
                'major': major,
                'minor': minor
            }
        
        return None
    
    def _generate_hierarchical_sidebar_content(self, organized_pages: dict) -> str:
        """生成层级化的侧边栏内容"""
        content = ""
        
        # 按主要序号排序
        for major in sorted(organized_pages.keys()):
            group = organized_pages[major]
            
            # 如果是最后的未分类组，添加标题
            if major == 999:
                content += "* 📋 其他页面\n"
            
            # 添加主页面
            if group['main_page']:
                main_page = group['main_page']
                content += f"* [{main_page['title']}]({main_page['path']})\n"
                
                # 添加该组的子页面
                if group['sub_pages']:
                    for minor in sorted(group['sub_pages'].keys()):
                        sub_page = group['sub_pages'][minor]
                        content += f"  * [{sub_page['title']}]({sub_page['path']})\n"
            else:
                # 如果没有主页面，但有子页面，直接列出子页面
                if group['sub_pages']:
                    if major != 999:  # 对于有序号但没有主页面的情况
                        content += f"* 📁 第 {major} 部分\n"
                    
                    for minor in sorted(group['sub_pages'].keys()):
                        sub_page = group['sub_pages'][minor]
                        indent = "  " if major != 999 else "  "
                        content += f"{indent}* [{sub_page['title']}]({sub_page['path']})\n"
            
            # 在每个主要分组后添加空行（除了最后一个）
            if major != max(organized_pages.keys()):
                content += "\n"
        
        return content
    
    def _generate_main_readme_with_pages(self, main_page_info: dict, pages: list):
        """生成包含页面导航的主 README.md"""
        
        readme_content = f"""# {main_page_info['project_name']}

> 🚀 从 DeepWiki 转换的文档站点

## 📖 文档导航

"""
        
        if pages:
            readme_content += f"本文档包含 **{len(pages)}** 个页面：\n\n"
            
            # 简单按字母顺序列出所有页面
            readme_content += "### 📚 所有页面\n\n"
            for page in sorted(pages, key=lambda p: p['title']):
                relative_path = None
                for processed_page in self.processed_pages:
                    if processed_page['slug'] == page['slug']:
                        relative_path = processed_page['file']
                        break
                
                if relative_path:
                    readme_content += f"- [{page['title']}]({relative_path})\n"
            readme_content += "\n"
        else:
            readme_content += "暂无页面内容。\n\n"
        
        readme_content += f"""

## 🔗 原始链接

- **DeepWiki 原始页面**: [{main_page_info['url']}]({main_page_info['url']})"""
        
        # 添加源码仓库链接
        if main_page_info.get('github_info', {}).get('repo_url'):
            repo_url = main_page_info['github_info']['repo_url']
            readme_content += f"""
- **源码仓库**: [{repo_url}]({repo_url})"""
        
        readme_content += f"""

## 📝 使用说明

此文档站点使用 [Docsify](https://docsify.js.org/) 构建，支持：

- 📱 响应式设计，支持移动端
- 🔍 全文搜索功能
- 🖼️ 图片缩放查看
- 📋 代码一键复制
- 📄 分页导航
- 📊 阅读进度显示

## 🚀 本地运行

```bash
# 进入文档目录
cd docs

# 启动本地服务器
python -m http.server 3000

# 或使用 Node.js
npx docsify serve
```

然后访问 http://localhost:3000

---

*由 [DeepWiki2Docsify](https://github.com/yourusername/deepwiki2docsify) 工具生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        readme_file = self.output_dir / "README.md"
        readme_file.write_text(readme_content, encoding='utf-8')
    
    def _generate_index_html(self, site_name: str = "DeepWiki 文档"):
        """生成 index.html"""
        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{site_name}</title>
  <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1" />
  <meta name="description" content="从 DeepWiki 转换的文档站点">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, minimum-scale=1.0">
  <link rel="stylesheet" href="//unpkg.com/docsify@4/lib/themes/vue.css">
  <style>
    .sidebar {{
      padding-top: 6px;
    }}
    .markdown-section {{
      max-width: 800px;
    }}
    .app-name-link {{
      color: var(--theme-color, #42b983) !important;
    }}
  </style>
</head>
<body>
  <div id="app">正在加载...</div>
  <script>
    window.$docsify = {{
      name: '{site_name}',
      repo: '',
      homepage: 'README.md',
      loadSidebar: true,
      autoHeader: true,
      subMaxLevel: 3,
      maxLevel: 4,
      search: {{
        maxAge: 86400000,
        paths: 'auto',
        placeholder: '搜索文档...',
        noData: '没有找到结果',
        depth: 6
      }},
      copyCode: {{
        buttonText: '复制代码',
        errorText: '复制失败',
        successText: '已复制到剪贴板'
      }},
      pagination: {{
        previousText: '上一页',
        nextText: '下一页',
        crossChapter: true,
        crossChapterText: true
      }},
      mermaid: {{
        theme: 'default'
      }}
    }}
  </script>
  <!-- Docsify v4 -->
  <script src="//unpkg.com/docsify@4"></script>
  <!-- Mermaid -->
  <script src="//unpkg.com/mermaid@9/dist/mermaid.min.js"></script>
  <script>
    mermaid.initialize({{
      theme: 'default',
      startOnLoad: false
    }});
  </script>
  <script src="//unpkg.com/docsify-mermaid@1/dist/docsify-mermaid.js"></script>
  <!-- 插件 -->
  <script src="//unpkg.com/docsify/lib/plugins/search.min.js"></script>
  <script src="//unpkg.com/docsify/lib/plugins/zoom-image.min.js"></script>
  <script src="//unpkg.com/docsify-copy-code@2"></script>
  <script src="//unpkg.com/docsify-pagination@2/dist/docsify-pagination.min.js"></script>
</body>
</html>'''
        
        index_file = self.output_dir / "index.html"
        index_file.write_text(html_content, encoding='utf-8')
        logger.info("🌐 生成 index.html...")


@click.command()
@click.argument('url', required=False, default='https://deepwiki.com/Dark-Athena/PlsqlRewrite4GaussDB-web/')
@click.option('--output', '-o', default='./docs', help='输出目录')
@click.option('--use-selenium/--no-selenium', default=True, help='是否使用 Selenium 处理动态内容')
@click.option('--multilingual', is_flag=True, help='生成多语言版本（中英文）')
@click.option('--force', is_flag=True, help='强制覆盖非空的输出目录（谨慎使用）')
def main(url: str, output: str, use_selenium: bool, multilingual: bool, force: bool):
    """
    DeepWiki 到 Docsify 转换器
    
    将 DeepWiki 在线页面转换为完整的 Docsify 文档站点
    
    默认URL: https://deepwiki.com/Dark-Athena/PlsqlRewrite4GaussDB-web/
    
    示例:
        python deepwiki_converter_fixed.py  # 使用默认URL
        python deepwiki_converter_fixed.py https://deepwiki.com/username/project  # 自定义URL
    """
    
    print("🚀 DeepWiki 到 Docsify 转换器 - 修复版本")
    print("=" * 50)
    
    if multilingual:
        print("🌐 多语言模式：将生成中英文双语文档")
    
    if force:
        print("⚠️ 强制覆盖模式：将覆盖输出目录中的现有文件")
    
    if not SELENIUM_AVAILABLE and use_selenium:
        print("⚠️  Selenium 未安装，将使用基础模式")
        print("💡 安装 Selenium: pip install selenium webdriver-manager")
        use_selenium = False
    
    converter = DeepWikiToDocsifyConverter(url, output, use_selenium, multilingual, force)
    result = converter.convert()
    
    if result['success']:
        print("\n🎉 转换成功！")
        print(f"📁 输出目录: {result['output_dir']}")
        print(f"📄 处理页面: {result['pages_processed']} 个")
        
        print(f"\n📋 项目信息:")
        print(f"   名称: {result['main_page']['project_name']}")
        print(f"   标题: {result['main_page']['title']}")
        print(f"   原始页面: {result['main_page']['url']}")
        
        print(f"\n💡 启动本地服务器:")
        print(f"   cd {output}")
        print("   python -m http.server 3000")
        print("   然后访问 http://localhost:3000")
        
        print(f"\n🌍 部署到 GitHub Pages:")
        print(f"   1. 将 {output} 目录内容推送到 GitHub 仓库")
        print(f"   2. 在仓库设置中启用 GitHub Pages")
        print(f"   3. 选择从根目录或 docs 目录部署")
        
    else:
        print(f"❌ 转换失败: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
