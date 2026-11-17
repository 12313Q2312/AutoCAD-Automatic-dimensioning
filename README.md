# Mechanical CAD Studio

## DraftPilot v2

用中文描述、录音或手绘草图发起四孔安装板设计。核对参数后，可在配置了云端模型的 Windows 本机发起 SolidWorks 2025 原生出图。完整的本机启动、支持范围及上机验收步骤见 [DraftPilot v2](docs/draftpilot-v2.md)。


**面向机械工程的本地 CAD 自动化工作台（工程预览版）。**

这个仓库从 AutoCAD Automatic Dimensioning 原型逐步扩展为两条工作流：
- **AutoCAD 自动标注**：保留现有 DWG 上传、样式选择和本地 AutoCAD COM / Agent 处理流程。
- **SolidWorks 自动建模（SW-01）**：在网页中输入带单位的中文尺寸描述或参数，生成确定性 `ModelPlan v1`、离线几何 SVG、验证报告。**暂未调用 SolidWorks，也不生成真实 SLDPRT/STEP。**

工作台还提供总览、任务中心和零件模板库。AutoCAD 模块沿用原有界面与 API；SolidWorks 的离线建模计划是全新受约束模块。

## 立即试用

安装 Python 3.11+。若只体验网页与 ModelPlan（无 AutoCAD 的 Windows/Linux 均可）：

```sh
python -m pip install "flask>=3.0,<5" "httpx>=0.28,<1" "Pillow>=10,<13" "requests>=2.32,<3"
python app.py
```

打开 **http://127.0.0.1:5000/**：进入统一工作台。点击 **SolidWorks 自动建模**，使用下列样例：

> 创建一块长120毫米、宽80毫米、厚8毫米的四孔安装板，孔径10毫米，X方向孔距90毫米，Y方向孔距50毫米。

预期得到：
1. 版本为 `1.0`、单位为毫米的建模计划；
2. 矩形基体 + 四孔贯穿切除，孔位中心为 `(±45,±25) mm`；
3. SVG 比例示意、几何校验结果、可下载 JSON；
4. **明确显示“未生成原生 CAD 文件”**。

点击 **AutoCAD 自动标注**可在内嵌页面操作原有 DWG 流程；独立旧入口为 **http://127.0.0.1:5000/autocad**。原有上传、任务和 Agent API 仍保留。若需真正连接 AutoCAD，在 Windows 环境另外安装 `requirements.txt` 的全部依赖以及受支持 AutoCAD；严禁使用私人或生产 DWG 原件直接实验。

## 工程结构

| 路径 | 作用 |
|---|---|
| [`static/studio.html`](static/studio.html) | 统一工作台，总览 / AutoCAD / SolidWorks / 任务 / 模板 |
| [`static/studio.css`](static/studio.css) 与 [`studio.js`](static/studio.js) | 响应式设计与交互 |
| [`solidworks_engine/`](solidworks_engine/) | 无外部 AI / CAD 依赖的模型计划、解析、几何验证与 SVG 预览 |
| [`solidworks_engine/modelplan-v1.schema.json`](solidworks_engine/modelplan-v1.schema.json) | 固定的结构化建模计划契约 |
| [`app.py`](app.py) | 统一网页入口 + 原有 AutoCAD API + `/api/model/plan` |
| [`static/index.html`](static/index.html) 与 [`static/app.js`](static/app.js) | 保留的 AutoCAD 标注页面 |
| [`dwg_processor/`](dwg_processor/) 与 [`dwg_agent.py`](dwg_agent.py) | 原有 DWG 标注与本地 Agent |
| [`tests/test_studio_model.py`](tests/test_studio_model.py) 与 [`test_studio_api.py`](tests/test_studio_api.py) | 几何约束与 Flask 路由回归 |
| [`docs/cad-studio-v0.1.md`](docs/cad-studio-v0.1.md) | 接口契约、验证边界与后续路线 |

## 验证与安全边界

```sh
python -m unittest discover -s tests -p "test_studio_*.py" -v
```

[CAD Studio offline CI](.github/workflows/cad-studio.yml) 在 Linux 与 Windows 检查 Python/JS 语法、解析算法、几何约束及本地 Flask 接口。其结果以对应运行的 head SHA 为准。

目前 WEB-01/SW-01 不提供真实 SolidWorks COM 调用、任意三维装配体、自由曲面或二维工程图自动重建。后续 SW-02、DWG-01 另行审批。真实 DWG 的尺寸精度、几何覆盖率尚未在 AutoCAD 中验收。服务默认仅监听 `127.0.0.1`，**未设计公网身份认证，不得直接部署为公网服务**。

**并行审查注意：** 现有 [AutoCAD File Safety PR #1](https://github.com/12313Q2312/AutoCAD-Automatic-dimensioning/pull/1) 是独立改进，尚未合入本特性分支；`main` 旧上传接口的安全限制仍应按该 PR 审核。将来合并两个 PR 时，需要手动核对 `app.py` 冲突并重跑回归。不得把已有本机上传、缓存或用户设置文件当作可清理资产。
