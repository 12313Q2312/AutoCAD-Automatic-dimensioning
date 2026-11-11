# AutoCAD Automatic Dimensioning

在 Windows 上批量给 DWG 图纸添加尺寸标注的实验项目。网页负责选择图纸、配置标注和查看结果，Python 通过 AutoCAD COM 执行绘图操作。

| 模块 | 用途 |
|---|---|
| [网页与任务服务](app.py) | 文件选择、任务进度和结果下载 |
| [规则标注](dwg_processor/auto_dim.py) | 根据几何实体和选定样式生成标注 |
| [AutoCAD 接口](dwg_processor/cad_com.py) | 启动或连接 AutoCAD，读取和操作图纸 |
| [本地代理](dwg_agent.py) | 执行任务，支持模拟流程 |
| [AI 适配器](ai_adapters) | 可选的模型接口 |

## 本机运行

需要 Windows、Python 和支持 COM 自动化的 AutoCAD。先在仓库目录安装依赖，然后启动服务：

```powershell
python -m pip install -r requirements.txt
python app.py
```

打开 `http://127.0.0.1:5000`，先用自己创建的简单 DWG 副本测试规则标注。要验证代理的任务流程，可以在另一个终端运行 `python dwg_agent.py --simulate`。

## 验证范围

当前版本面向单机试验，服务默认监听本机。真实 DWG 的图层、单位、标注样式和几何覆盖率需要在 AutoCAD 中抽检。客户图纸、运行日志、账号密钥和使用记录不随源码发布。
