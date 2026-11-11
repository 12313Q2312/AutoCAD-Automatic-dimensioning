# AutoCAD Automatic Dimensioning

在 Windows 上批量给 DWG 图纸添加尺寸标注的实验项目。网页负责选择图纸、配置标注和查看结果，Python 通过 AutoCAD COM 执行绘图操作。

## 本机运行

需要 Windows、Python 和支持 COM 自动化的 AutoCAD。在仓库目录安装依赖并启动服务：

```powershell
python -m pip install -r requirements.txt
python app.py
```

打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)，用自己创建的简单 DWG **副本**试跑。选择图纸与标注样式，执行后用 AutoCAD 打开输出文件，核对尺寸值、单位和标注位置。

没有 CAD 时，可以先用网页查看流程和国标样式预设。要试用模拟代理，在另一个终端运行 `python dwg_agent.py --simulate`。

## 当前验证

Windows 上已检查首页、样式和脚本加载，以及国标样式接口返回。真实 DWG 的规则标注、尺寸精度和几何覆盖率待在 AutoCAD 中验收。服务默认仅监听本机。

## 代码入口

| 模块 | 用途 |
|---|---|
| [网页与任务服务](app.py) | 文件选择、任务进度和结果下载 |
| [规则标注](dwg_processor/auto_dim.py) | 根据几何实体和选定样式生成标注 |
| [AutoCAD 接口](dwg_processor/cad_com.py) | 启动或连接 AutoCAD，读取和操作图纸 |
| [本地代理](dwg_agent.py) | 执行任务，支持模拟流程 |
| [AI 适配器](ai_adapters) | 可选的模型接口 |
