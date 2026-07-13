---
Task ID: flask-icu-app
Agent: main
Task: 用 Flask + Ubuntu 建立 ICU 数据管理网站,前端模板继承,后端 SQL,参考 farm-mall 项目,数据来自 ICU数据.xlsx

Work Log:
- 分析 Excel 文件:8 个分表(血常规/生化全套/甲功五项/贫血三项/血气电解质/细菌感染二项/心肌标志物二项/纤溶全套)
- 安装 Flask + Flask-SQLAlchemy;使用已有 pandas/openpyxl/scikit-learn
- 创建 Flask 应用 (icu_app/):动态建表(每分表一张 SQL 表)、Excel 数据导入、线性回归预测
- 实现 base.html 模板(侧边导航栏,8 个分表选项)+ sheet.html 模板(继承 base,含可编辑表格、折线图、预测图、新增/删除记录模态框)
- 配色:teal(翡翠绿)主色,医疗主题,响应式(移动端汉堡菜单)
- 图表:Chart.js 折线图(多指标切换)+ 预测图(线性回归,虚线预测未来3点,显示斜率/截距/R²)
- 数据接口:内联编辑(失焦自动保存 AJAX)、新增记录(模态框)、删除行(confirm)
- 端口托管:Flask 运行在 5000 端口,通过 Next.js API 路由(/api/start-flask)以 detached 子进程方式启动,确保跨 bash 命令存活;Next.js / 页面用全屏 iframe 经网关(?XTransformPort=5000)加载 Flask
- Agent Browser 端到端验证:8 个导航项渲染、表格数据正确、折线图/预测图渲染(非空像素验证)、内联编辑存库、新增记录存库、删除记录、移动端汉堡菜单、sticky footer
- VLM 视觉评估:布局清晰、配色协调、图表正常、导航直观
- Lint 通过(0 错误 0 警告)

Stage Summary:
- Flask 应用位于 /home/z/my-project/icu_app/,入口 app.py
- 数据库 icu.db (SQLite + SQLAlchemy),8 张动态数据表 + 1 张元信息表
- 模板继承:base.html -> sheet.html / error.html
- 通过网关访问:用户在预览面板看到的是 Flask 应用(经 Next.js iframe 透传)
- Flask 由 Next.js 进程托管,稳定常驻
