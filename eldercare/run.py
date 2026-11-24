"""本地启动入口：python run.py 后浏览器访问 http://127.0.0.1:8000"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.web.main:app", host="127.0.0.1", port=8000, reload=False)
