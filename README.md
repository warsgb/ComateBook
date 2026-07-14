# WPS Comate 红宝书

WPS Comate 蓝皮书的网页版，提供左侧树状导航栏，适合在线阅读。

## 内容

- 35 个章节（5 篇 + 附录），覆盖使用手册、场景实践、进阶技巧、岗位落地
- 406 张配图
- 单页应用，所有内容嵌入 index.html，离线可用

## 使用

直接用浏览器打开 `index.html`，或启动本地服务器：

```bash
cd ComateBook
python3 -m http.server 8899
# 浏览器访问 http://localhost:8899
```

## 重新构建

如需从源 Markdown 重新生成：

```bash
pip install markdown pymdown-extensions
python3 build.py
```

源文件位于 `cmbluebook/` 目录（不包含在本仓库中）。
