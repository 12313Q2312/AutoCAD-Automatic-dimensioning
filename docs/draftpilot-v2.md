# DraftPilot v2 | 四孔安装板

打开 `http://127.0.0.1:5000/draftpilot`。界面按描述、追问、预览、导出逐步显示操作。现有离线 ModelPlan v1 仍可从 `/studio#solidworks` 打开。

## 开发版启动

在安装并启动 SolidWorks 2025 的 Windows 工作站上，使用 PowerShell 在仓库目录执行：

```powershell
python -m pip install -r requirements.txt
$env:DRAFTPILOT_MODEL = "<支持 Chat Completions、图片输入和严格 JSON Schema 的模型 ID>"
$env:DRAFTPILOT_API_KEY = "<提供商密钥>"
# 可选，配置音频转写模型后，页面显示录音按钮。
$env:DRAFTPILOT_TRANSCRIPTION_MODEL = "<提供商的语音转写模型 ID>"
python app.py
```

密钥由运行服务的环境读取。普通用户使用网页按钮即可。默认请求地址为 `https://api.openai.com/v1`。若使用其他兼容服务，可在同一环境配置 `DRAFTPILOT_API_BASE`，并在上机前验证其严格 JSON Schema 和图片接口。模型、API 地址和密钥由启动人配置。页面提交的描述、草图和转写用音频会发给所配置的云端服务。提供商的记录政策以实际配置为准。这一开发版使用本机回环地址。仓库中的旧 AutoCAD 路由也在 Flask 应用中，整个应用须保留在受信任的本机环境。

原生导出读取 SolidWorks 的默认零件模板和单页 A4 或以上工程图模板。需要指定绝对路径时，用 `DRAFTPILOT_PART_TEMPLATE` 和 `DRAFTPILOT_DRAWING_TEMPLATE` 设置可信的 `.prtdot`、`.drwdot`。在同一 Windows 用户会话启动 SolidWorks 与 Flask。导出运行在已经打开的 SolidWorks 2025 中，会切换到本次生成的新文档，结束时尝试关闭这些文档。

## 使用与验收

1. 从“做一块十二乘八厘米的板，四角打通孔”开始。依次补上厚 8 mm、孔径 10 mm、横向孔距 90 mm、纵向孔距 50 mm。核对四个孔中心的 X 为 ±45 mm，Y 为 ±25 mm。
2. 说“左上孔向右移 3 mm”。左上孔从 `(-45, 25)` 移到 `(-42, 25)`，另外三个孔保持原位。尝试移动出板边，界面应报错；可以返回上一个有效预览。点“恢复上一版”可恢复成功修改前的计划。
3. 试“右边两个孔加大一些”，再回答“直径 12 毫米”。只改变右侧两孔。单孔改过一轴位置后，重新指令修改该轴整体孔距时需要明确指定孔。
4. 上传一张正视矩形四角孔的 PNG/JPEG 草图。草图只提供可识别的布局，单凭草图不会出尺寸。原型支持四个角各一个通孔，初建由口述尺寸确定对称布局，随后可以修改孔的位置和直径。录音转写先显示文字供核对，确认后再提交。
5. 在 SolidWorks 2025 中点击“生成 SolidWorks 文件”，将 ZIP 里的文件解压到同一文件夹。打开零件、工程图及 PDF，核对三视图、孔位、孔径和板厚，确认工程图引用的是同目录生成的零件。用新修改再导出一次检查重新生成的尺寸、PDF 和旧版本。
6. 工程图用三视图及原生文字尺寸说明列出外形尺寸与孔坐标。尺寸说明用于几何核对，手动在 SolidWorks 中编辑时需重新生成或更新说明。材料、制造公差以及关联尺寸线需在发布制造图前确认。

## 实现边界

- 云端只返回建议参数、缺项和修改目标。服务器根据受支持的操作重新构建 ModelPlan v2，校验数字、象限和孔间距。用户在预览中查看数值，再显式触发原生出图。
- 原生适配器从新文档生成实体，在打包前读取实际孔的圆柱面位置和半径，并用外包框筛查外形尺寸。导出保存在任务专用临时目录，ZIP 使用独立的零件和工程图名称。
- 升级分支基于 Draft PR #2。云端结构化请求、转写入口及文件流程有离线测试。真实服务与 SolidWorks 2025 的联合上机验收，以实际运行记录为准。
- 草图文件大小上限 2 MiB。录音不超过 30 秒。上一版记录保存在当前页面中，已下载的 ZIP 可另存。

## 开发回归

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_studio_*.py" -v
node --check static/draftpilot.js
```
