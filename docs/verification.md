# 第一版验证记录

验证时间：2026-09-30。

- Python 3.12.14、pdfplumber 0.11.8、tkinterdnd2 0.6.3。
- 26 项自动化测试通过。
- 在 Linux 虚拟显示中实际运行了 Tk 9.0.4 窗口；拖拽扩展 tkdnd 2.10.2 成功加载。
- 检查了文件选择/拖入路径解析、后台读取、进度与按钮状态、编辑、复制、保存和图片复制、密码重试、扫描件提示、取消。
- 已对自制三页 PDF 的页面渲染及 Markdown 输出做人工核对。
- Windows/macOS 尚未在真实系统上运行验证；字体和原生拖拽效果由平台决定。
- 尚未使用你的老师发的真实 PDF；当前对复杂公式、三栏、跨页段落、扫描件和复杂合并单元格有 README 说明的限制。

运行自动化测试：
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v

