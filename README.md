# pension_app
家庭+社区+机构性养老

## 工程结构

- `eldercare/` —— 首版后端工程（Python + FastAPI + SQLite + WebSocket），含浏览器可访问的移动端演示页。
- `PRD.md` —— 产品需求基线。
- `开发计划.md` —— 阶段 WBS 与两端一致性方案。
- `养老App线框原型.html` —— 低保真可点击线框原型。
- `养老App功能与页面清单.docx` —— 功能 / 页面清单。

## 快速开始

详见 `eldercare/README.md`。在 `eldercare` 目录下：

```powershell
$env:PYTHONPATH="."
python run.py
```

浏览器访问 <http://127.0.0.1:8000>，演示账号：

- 老人端 `13300000001`，子女端 `13300000002`，固定验证码 `123456`。

## 测试

```powershell
cd eldercare
$env:PYTHONPATH="."
python -m pytest -q
```
