#!/usr/bin/env python3
"""
Build ComateBook: Convert cmredbook markdown files to a single-page web app.
- Left sidebar: tree navigation (collapsible)
- Right: reading area
- Fixes H2/H3 numbering to match actual chapter numbers
- Removes Chapter 24
- Swaps Chapter 28 and 29 order
"""

import os
import re
import json
import shutil
import markdown

SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cmredbook')
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Chapters to skip entirely
SKIP_CHAPTERS = {'第 24 章'}

# Swap these chapters' order (they will appear in reverse order in navigation)
SWAP_PAIRS = [('第 28 章', '第 29 章')]

# Chinese numeral to int mapping for part ordering
CHINESE_NUMS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def extract_part_num(name):
    """Extract part number from Chinese numeral: '第一篇' -> 1, '第二篇' -> 2"""
    m = re.search(r'第([一二三四五六七八九十]+)篇', name)
    if m:
        s = m.group(1)
        if s == '十':
            return 10
        if '十' in s:
            parts = s.split('十')
            tens = CHINESE_NUMS.get(parts[0], 1) if parts[0] else 1
            ones = CHINESE_NUMS.get(parts[1], 0) if parts[1] else 0
            return tens * 10 + ones
        return CHINESE_NUMS.get(s, 99)
    return 99  # Non-matching parts (like 附录) go last


def extract_chapter_num(dirname):
    """Extract chapter number from directory name like '第 21 章 打造技能' -> 21"""
    m = re.match(r'第\s*(\d+)\s*章', dirname)
    return int(m.group(1)) if m else None


def fix_heading_numbers(content, correct_chapter_num):
    """
    Fix H2 and H3 heading numbers to match the actual chapter number.
    e.g., '## 18.1 ...' in chapter 21 becomes '## 21.1 ...'
    Also fixes H3 like '### 18.2.1 ...' -> '### 21.2.1 ...'
    """
    if correct_chapter_num is None:
        return content

    lines = content.split('\n')
    old_chapter_num = None

    # First pass: detect the old chapter number from the first numbered H2
    for line in lines:
        m = re.match(r'^##\s+(\d+)\.\d+', line)
        if m:
            old_chapter_num = int(m.group(1))
            break

    if old_chapter_num is None or old_chapter_num == correct_chapter_num:
        return content  # No fix needed

    old_prefix = str(old_chapter_num)
    new_prefix = str(correct_chapter_num)

    # Replace H2: ## 18.1 -> ## 21.1
    # Replace H3: ### 18.2.1 -> ### 21.2.1
    fixed_lines = []
    for line in lines:
        # H2 pattern: ## XX.Y title
        m2 = re.match(r'^(##\s+)' + old_prefix + r'\.(\d+)', line)
        if m2:
            line = m2.group(1) + new_prefix + '.' + m2.group(2) + line[m2.end():]
        else:
            # H3 pattern: ### XX.Y.Z title
            m3 = re.match(r'^(###\s+)' + old_prefix + r'\.(\d+\.\d+)', line)
            if m3:
                line = m3.group(1) + new_prefix + '.' + m3.group(2) + line[m3.end():]
        fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def sort_chapters(chapters):
    """Sort chapters by chapter number, apply skip and swap rules."""
    result = []
    for ch in chapters:
        dirname = ch['dirname']
        # Skip chapters
        if any(skip in dirname for skip in SKIP_CHAPTERS):
            continue
        result.append(ch)

    # Apply swaps
    for a, b in SWAP_PAIRS:
        idx_a = None
        idx_b = None
        for i, ch in enumerate(result):
            if a in ch['dirname']:
                idx_a = i
            if b in ch['dirname']:
                idx_b = i
        if idx_a is not None and idx_b is not None:
            result[idx_a], result[idx_b] = result[idx_b], result[idx_a]

    return result


def process_markdown(md_path, correct_chapter_num):
    """Read and process a markdown file: fix numbering, convert to HTML."""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix heading numbers
    content = fix_heading_numbers(content, correct_chapter_num)

    # Convert to HTML
    md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'sane_lists', 'nl2br'])
    html = md.convert(content)

    # Fix image paths: convert relative asset paths to img/ paths
    # assets/xxx.png -> img/<chapter_slug>/xxx.png
    # We need to figure out the chapter slug

    return html


def slugify_chapter_dir(dirpath):
    """Create a safe directory name for images from chapter path."""
    # Replace spaces with underscores, keep Chinese chars
    slug = os.path.basename(dirpath).replace(' ', '_')
    return slug


def slugify_section_dir(full_dirpath, source_root):
    """Create full image path slug from source root to chapter dir."""
    rel = os.path.relpath(full_dirpath, source_root)
    parts = rel.split(os.sep)
    slug_parts = [p.replace(' ', '_') for p in parts]
    return '/'.join(slug_parts)


def collect_images(source_dir):
    """Collect all image files (png, jpg, gif, svg) from a directory and its assets subdirectory."""
    images = {}
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                src = os.path.join(root, f)
                images[f] = src  # basename -> full path
    return images


def find_image_source(img_name, chapter_dir, source_root):
    """Find the source path of an image by name, searching chapter dir first."""
    # First check assets/ in the chapter dir
    assets_dir = os.path.join(chapter_dir, 'assets')
    candidate = os.path.join(assets_dir, img_name)
    if os.path.exists(candidate):
        return candidate
    # Check chapter dir itself
    candidate = os.path.join(chapter_dir, img_name)
    if os.path.exists(candidate):
        return candidate
    # Search recursively in chapter dir
    for root, dirs, files in os.walk(chapter_dir):
        if img_name in files:
            return os.path.join(root, img_name)
    return None


def build():
    # Clean output img directory
    img_out = os.path.join(OUTPUT_DIR, 'img')
    if os.path.exists(img_out):
        shutil.rmtree(img_out)
    os.makedirs(img_out)

    # Collect all sections
    sections = []  # List of (part_name, [chapters])
    all_pages = []  # Flat list of pages with metadata

    # Get all parts (top-level dirs under source), sorted by Chinese numeral
    part_dirs = []
    for name in os.listdir(SOURCE_DIR):
        full = os.path.join(SOURCE_DIR, name)
        if os.path.isdir(full) and name != '附录':
            part_dirs.append(name)
    part_dirs.sort(key=extract_part_num)

    # Also handle appendix
    appendix_dir = os.path.join(SOURCE_DIR, '附录')
    has_appendix = os.path.isdir(appendix_dir)

    nav_tree = []  # For JSON navigation
    content_map = {}  # page_id -> {title, html, part, prev, next}
    page_order = []  # Ordered list of page_ids

    all_pages_data = []

    # Process root index.md first
    root_index = os.path.join(SOURCE_DIR, 'index.md')
    if os.path.exists(root_index):
        with open(root_index, 'r', encoding='utf-8') as f:
            content = f.read()
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'sane_lists', 'nl2br'])
        html = md.convert(content)
        page_id = 'cover'
        content_map[page_id] = {
            'title': '封面',
            'html': html,
            'part': '封面',
            'is_cover': True
        }
        page_order.append(page_id)
        all_pages_data.append({
            'id': page_id,
            'title': '封面',
            'part': '封面',
            'children': []
        })

    # Process each part
    for part_name in part_dirs:
        part_dir = os.path.join(SOURCE_DIR, part_name)
        if not os.path.isdir(part_dir):
            continue

        # Read part index.md
        part_index = os.path.join(part_dir, 'index.md')
        part_title = part_name
        if os.path.exists(part_index):
            with open(part_index, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith('#'):
                    part_title = first_line.lstrip('#').strip()

        part_node = {
            'title': part_title,
            'dir': part_name,
            'children': []
        }

        # Get all chapter directories
        chapter_dirs = []
        for name in os.listdir(part_dir):
            full = os.path.join(part_dir, name)
            if os.path.isdir(full):
                chapter_dirs.append(name)

        # Sort by chapter number
        def chapter_sort_key(name):
            num = extract_chapter_num(name)
            if num is not None:
                return (0, num)
            return (1, name)

        chapter_dirs.sort(key=chapter_sort_key)

        # Build chapter objects
        chapter_objs = []
        for ch_name in chapter_dirs:
            ch_dir = os.path.join(part_dir, ch_name)
            ch_index = os.path.join(ch_dir, 'index.md')
            if not os.path.exists(ch_index):
                continue
            chapter_objs.append({
                'dirname': ch_name,
                'dirpath': ch_dir,
                'index_path': ch_index
            })

        # Apply skip and swap
        chapter_objs = sort_chapters(chapter_objs)

        for ch_obj in chapter_objs:
            ch_name = ch_obj['dirname']
            ch_dir = ch_obj['dirpath']
            ch_index = ch_obj['index_path']
            ch_num = extract_chapter_num(ch_name)

            # Read and process markdown
            with open(ch_index, 'r', encoding='utf-8') as f:
                content = f.read()

            # Fix heading numbers
            content = fix_heading_numbers(content, ch_num)

            # Strip the first H1 (title) since it's rendered separately by JS
            content = re.sub(r'^#\s+.+\n?', '', content, count=1)

            # Fix image paths: assets/xxx.png -> img/<slug>/xxx.png
            img_slug = slugify_section_dir(ch_dir, SOURCE_DIR)
            img_out_dir = os.path.join(OUTPUT_DIR, 'img', img_slug)
            os.makedirs(img_out_dir, exist_ok=True)

            # Find and copy images
            # First handle assets/ directory images
            assets_dir = os.path.join(ch_dir, 'assets')
            if os.path.isdir(assets_dir):
                for img_name in os.listdir(assets_dir):
                    if img_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                        src = os.path.join(assets_dir, img_name)
                        dst = os.path.join(img_out_dir, img_name)
                        if not os.path.exists(dst):
                            shutil.copy2(src, dst)

            # Replace image paths in content
            # Pattern: ![](assets/xxx.png) or ![](xxx.png)
            def replace_img_path(m):
                img_path = m.group(2)
                img_name = os.path.basename(img_path)
                return f'{m.group(1)}img/{img_slug}/{img_name}{m.group(3)}'

            content = re.sub(r'(!\[.*?\]\()(?:assets/)?([^)]+)(\))', replace_img_path, content)

            # Convert to HTML
            md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'sane_lists', 'nl2br'])
            html = md.convert(content)

            # Get title from first H1
            title = ch_name
            title_m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_m:
                title = title_m.group(1).strip()

            page_id = ch_name.replace(' ', '_')
            content_map[page_id] = {
                'title': title,
                'html': html,
                'part': part_title,
                'chapter_num': ch_num
            }
            page_order.append(page_id)

            part_node['children'].append({
                'id': page_id,
                'title': title,
                'chapter_num': ch_num
            })

        nav_tree.append(part_node)
        all_pages_data.append({
            'id': part_name.replace(' ', '_'),
            'title': part_title,
            'children': part_node['children']
        })

    # Process appendix
    if has_appendix:
        appendix_index = os.path.join(appendix_dir, 'index.md')
        appendix_title = '附录'
        if os.path.exists(appendix_index):
            with open(appendix_index, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith('#'):
                    appendix_title = first_line.lstrip('#').strip()

        appendix_node = {
            'title': appendix_title,
            'dir': '附录',
            'children': []
        }

        # Get appendix subdirectories
        app_dirs = sorted([d for d in os.listdir(appendix_dir) if os.path.isdir(os.path.join(appendix_dir, d))])
        for app_name in app_dirs:
            app_dir = os.path.join(appendix_dir, app_name)
            app_index = os.path.join(app_dir, 'index.md')
            if not os.path.exists(app_index):
                continue

            with open(app_index, 'r', encoding='utf-8') as f:
                content = f.read()

            # Strip the first H1 (title) since it's rendered separately by JS
            content = re.sub(r'^#\s+.+\n?', '', content, count=1)

            # Fix image paths
            img_slug = slugify_section_dir(app_dir, SOURCE_DIR)
            img_out_dir = os.path.join(OUTPUT_DIR, 'img', img_slug)
            os.makedirs(img_out_dir, exist_ok=True)

            assets_dir = os.path.join(app_dir, 'assets')
            if os.path.isdir(assets_dir):
                for img_name in os.listdir(assets_dir):
                    if img_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                        src = os.path.join(assets_dir, img_name)
                        dst = os.path.join(img_out_dir, img_name)
                        if not os.path.exists(dst):
                            shutil.copy2(src, dst)

            content = re.sub(r'(!\[.*?\]\()(?:assets/)?([^)]+)(\))', replace_img_path, content)

            md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'sane_lists', 'nl2br'])
            html = md.convert(content)

            title = app_name
            title_m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_m:
                title = title_m.group(1).strip()

            page_id = app_name.replace(' ', '_')
            content_map[page_id] = {
                'title': title,
                'html': html,
                'part': appendix_title
            }
            page_order.append(page_id)

            appendix_node['children'].append({
                'id': page_id,
                'title': title,
                'chapter_num': None
            })

        nav_tree.append(appendix_node)

    # Also handle 课外阅读
    extra_reading_dirs = []
    for part_name in part_dirs:
        part_dir = os.path.join(SOURCE_DIR, part_name)
        for name in os.listdir(part_dir):
            full = os.path.join(part_dir, name)
            if os.path.isdir(full) and '课外阅读' in name:
                # Already handled if it was in chapter_dirs
                # Actually it would have been skipped because it doesn't match "第 X 章"
                # Let's check if it was included
                pass

    # Build prev/next links
    for i, pid in enumerate(page_order):
        if pid in content_map:
            content_map[pid]['prev'] = page_order[i-1] if i > 0 else None
            content_map[pid]['next'] = page_order[i+1] if i < len(page_order)-1 else None

    # Generate HTML
    nav_json = json.dumps(nav_tree, ensure_ascii=False)
    content_json = json.dumps(content_map, ensure_ascii=False)

    html_template = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WPS Comate 红宝书</title>
<style>
:root {
  --sidebar-width: 320px;
  --bg: #ffffff;
  --fg: #1a1a2e;
  --fg-light: #555;
  --sidebar-bg: #f7f8fa;
  --sidebar-hover: #e8eaf0;
  --sidebar-active: #fbe9e7;
  --accent: #c0392b;
  --accent-light: #e74c3c;
  --border: #e2e8f0;
  --code-bg: #f4f4f7;
  --shadow: 0 2px 8px rgba(0,0,0,0.08);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.8;
  -webkit-font-smoothing: antialiased;
}

/* Layout */
#app {
  display: flex;
  min-height: 100vh;
}

/* Sidebar */
#sidebar {
  width: var(--sidebar-width);
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  overflow-y: auto;
  z-index: 100;
  transition: transform 0.3s ease;
}

#sidebar::-webkit-scrollbar { width: 6px; }
#sidebar::-webkit-scrollbar-track { background: transparent; }
#sidebar::-webkit-scrollbar-thumb { background: #cbd5e0; border-radius: 3px; }

.sidebar-header {
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--border);
}

.sidebar-header h1 {
  font-size: 18px;
  font-weight: 700;
  color: var(--fg);
  margin-bottom: 4px;
}

.sidebar-header .subtitle {
  font-size: 12px;
  color: var(--fg-light);
}

.search-box {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.search-box input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.search-box input:focus {
  border-color: var(--accent-light);
}

/* Navigation tree */
.nav-tree {
  padding: 8px 0;
}

.nav-part {
  margin-bottom: 4px;
}

.nav-part-title {
  padding: 10px 16px 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-light);
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-part-title:hover {
  color: var(--accent);
}

.nav-part-title .toggle {
  font-size: 10px;
  transition: transform 0.2s;
  display: inline-block;
}

.nav-part.collapsed .toggle {
  transform: rotate(-90deg);
}

.nav-part.collapsed .nav-children {
  display: none;
}

.nav-children {
  padding: 0 0 4px 0;
}

.nav-chapter {
  padding: 6px 16px 6px 32px;
  font-size: 13px;
  color: var(--fg);
  cursor: pointer;
  transition: background 0.15s;
  border-left: 3px solid transparent;
}

.nav-chapter:hover {
  background: var(--sidebar-hover);
}

.nav-chapter.active {
  background: var(--sidebar-active);
  border-left-color: var(--accent);
  color: var(--accent);
  font-weight: 500;
}

/* Main content */
#main {
  flex: 1;
  margin-left: var(--sidebar-width);
  padding: 40px 60px 80px;
  max-width: 900px;
  min-width: 0;
}

.content-wrapper {
  max-width: 780px;
  margin: 0 auto;
}

/* Typography */
h1, h2, h3, h4, h5, h6 {
  margin-top: 1.5em;
  margin-bottom: 0.6em;
  font-weight: 700;
  line-height: 1.3;
}

h1 {
  font-size: 28px;
  border-bottom: 2px solid var(--border);
  padding-bottom: 12px;
  margin-top: 0;
}

h2 {
  font-size: 22px;
  color: var(--fg);
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}

h3 {
  font-size: 18px;
}

h4 {
  font-size: 16px;
}

p {
  margin-bottom: 1em;
}

a {
  color: var(--accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

strong {
  font-weight: 700;
}

blockquote {
  border-left: 4px solid var(--accent-light);
  padding: 8px 16px;
  margin: 1em 0;
  background: #fff5f5;
  color: var(--fg);
  border-radius: 0 4px 4px 0;
}

blockquote p {
  margin-bottom: 0;
}

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
  font-size: 14px;
}

th, td {
  padding: 10px 14px;
  border: 1px solid var(--border);
  text-align: left;
}

th {
  background: var(--sidebar-bg);
  font-weight: 600;
}

tr:nth-child(even) {
  background: #fafbfc;
}

/* Code */
code {
  font-family: "SF Mono", "Fira Code", "JetBrains Mono", Consolas, monospace;
  background: var(--code-bg);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.9em;
}

pre {
  background: #2d2d2d;
  color: #f8f8f2;
  padding: 16px 20px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 1em 0;
  font-size: 13px;
  line-height: 1.5;
}

pre code {
  background: transparent;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

/* Images */
img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  box-shadow: var(--shadow);
  margin: 1em 0;
  display: block;
}

/* HR */
hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 2em 0;
}

/* Lists */
ul, ol {
  padding-left: 1.8em;
  margin-bottom: 1em;
}

li {
  margin-bottom: 0.3em;
}

/* Navigation footer */
.nav-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

.nav-footer button {
  padding: 8px 20px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--fg);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.nav-footer button:hover {
  background: var(--sidebar-hover);
  border-color: var(--accent-light);
}

.nav-footer button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Back to top */
#back-to-top {
  position: fixed;
  bottom: 30px;
  right: 30px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s;
  z-index: 99;
  box-shadow: var(--shadow);
}

#back-to-top.visible {
  opacity: 1;
}

#back-to-top:hover {
  background: var(--accent-light);
}

/* Mobile */
#mobile-toggle {
  display: none;
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 101;
  background: var(--accent);
  color: white;
  border: none;
  width: 40px;
  height: 40px;
  border-radius: 6px;
  font-size: 20px;
  cursor: pointer;
  box-shadow: var(--shadow);
}

@media (max-width: 768px) {
  #sidebar {
    transform: translateX(-100%);
  }

  #sidebar.open {
    transform: translateX(0);
  }

  #main {
    margin-left: 0;
    padding: 60px 20px 60px;
  }

  #mobile-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .content-wrapper {
    max-width: 100%;
  }
}
</style>
</head>
<body>

<button id="mobile-toggle">&#9776;</button>

<div id="app">
  <div id="sidebar">
    <div class="sidebar-header">
      <h1>WPS Comate 红宝书</h1>
      <div class="subtitle">从入门到精通的完整指南</div>
    </div>
    <div class="search-box">
      <input type="text" id="search" placeholder="搜索章节..." />
    </div>
    <div class="nav-tree" id="nav-tree"></div>
  </div>

  <div id="main">
    <div class="content-wrapper" id="content"></div>
    <div class="nav-footer">
      <button id="prev-btn" onclick="goPrev()">&#8592; 上一章</button>
      <button id="next-btn" onclick="goNext()">下一章 &#8594;</button>
    </div>
  </div>
</div>

<button id="back-to-top" onclick="scrollTop()">&#8593;</button>

<script>
const NAV_TREE = ''' + nav_json + ''';
const CONTENT = ''' + content_json + ''';

let currentPageId = null;
let pageOrder = [];

// Build page order from nav tree
function buildPageOrder() {
  pageOrder = [];
  for (const part of NAV_TREE) {
    if (part.children) {
      for (const ch of part.children) {
        pageOrder.push(ch.id);
      }
    }
  }
}

// Render navigation tree
function renderNav() {
  const container = document.getElementById('nav-tree');
  container.innerHTML = '';
  let firstPart = true;

  for (const part of NAV_TREE) {
    const partDiv = document.createElement('div');
    partDiv.className = 'nav-part' + (firstPart ? '' : ' collapsed');
    firstPart = false;

    const titleDiv = document.createElement('div');
    titleDiv.className = 'nav-part-title';
    titleDiv.innerHTML = '<span class="toggle">&#9660;</span> ' + part.title;
    titleDiv.onclick = function() {
      partDiv.classList.toggle('collapsed');
    };

    const childrenDiv = document.createElement('div');
    childrenDiv.className = 'nav-children';

    if (part.children) {
      for (const ch of part.children) {
        const chDiv = document.createElement('div');
        chDiv.className = 'nav-chapter';
        chDiv.textContent = ch.title;
        chDiv.dataset.id = ch.id;
        chDiv.onclick = function() {
          loadPage(ch.id);
        };
        childrenDiv.appendChild(chDiv);
      }
    }

    partDiv.appendChild(titleDiv);
    partDiv.appendChild(childrenDiv);
    container.appendChild(partDiv);
  }
}

// Load a page
function loadPage(pageId) {
  if (!CONTENT[pageId]) return;

  currentPageId = pageId;
  const data = CONTENT[pageId];
  const contentDiv = document.getElementById('content');

  let html = '';
  if (data.is_cover) {
    html = '<div style="text-align:center;padding:60px 0;">' + data.html + '</div>';
  } else {
    html = '<h1>' + data.title + '</h1>' + data.html;
  }
  contentDiv.innerHTML = html;

  // Update active nav item
  document.querySelectorAll('.nav-chapter').forEach(el => {
    el.classList.toggle('active', el.dataset.id === pageId);
  });

  // Expand the part containing this page
  document.querySelectorAll('.nav-part').forEach(partDiv => {
    const chapters = partDiv.querySelectorAll('.nav-chapter');
    let found = false;
    chapters.forEach(ch => {
      if (ch.dataset.id === pageId) found = true;
    });
    if (found) {
      partDiv.classList.remove('collapsed');
    }
  });

  // Update prev/next buttons
  const idx = pageOrder.indexOf(pageId);
  document.getElementById('prev-btn').disabled = idx <= 0;
  document.getElementById('next-btn').disabled = idx >= pageOrder.length - 1;

  // Scroll to top
  window.scrollTo(0, 0);
}

function goPrev() {
  const idx = pageOrder.indexOf(currentPageId);
  if (idx > 0) loadPage(pageOrder[idx - 1]);
}

function goNext() {
  const idx = pageOrder.indexOf(currentPageId);
  if (idx < pageOrder.length - 1) loadPage(pageOrder[idx + 1]);
}

// Search
document.getElementById('search').addEventListener('input', function(e) {
  const query = e.target.value.toLowerCase().trim();
  document.querySelectorAll('.nav-chapter').forEach(el => {
    if (!query) {
      el.style.display = '';
      return;
    }
    const text = el.textContent.toLowerCase();
    el.style.display = text.includes(query) ? '' : 'none';
  });

  // Expand all parts when searching
  if (query) {
    document.querySelectorAll('.nav-part').forEach(p => p.classList.remove('collapsed'));
  }
});

// Back to top
window.addEventListener('scroll', function() {
  const btn = document.getElementById('back-to-top');
  btn.classList.toggle('visible', window.scrollY > 400);
});

function scrollTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Keyboard navigation
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowLeft') goPrev();
  if (e.key === 'ArrowRight') goNext();
});

// Mobile toggle
document.getElementById('mobile-toggle').addEventListener('click', function() {
  document.getElementById('sidebar').classList.toggle('open');
});

// Init
buildPageOrder();
renderNav();
// Load first page
if (pageOrder.length > 0) {
  loadPage(pageOrder[0]);
}
</script>
</body>
</html>'''

    # Write output
    output_path = os.path.join(OUTPUT_DIR, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)

    # Count stats
    img_count = 0
    for root, dirs, files in os.walk(img_out):
        img_count += len([f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg'))])

    print(f'Build complete: {len(page_order)} pages, {img_count} images')
    print(f'Output: {output_path}')


if __name__ == '__main__':
    build()
