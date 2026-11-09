# 介绍图片与截图

采集日期：2026-11-09。图片仅包含本项目界面和自行编写的演示内容，不含用户私有项目、密钥或真实客户素材。

| 文件 | 来源 | 应如何理解 |
| --- | --- | --- |
| cineflow-cover.svg / cineflow-cover.png | 本项目绘制的 SVG 品牌插画及其浏览器渲染图 | 三只杯子是示意插画，不是模型生成样片 |
| workspace.png | 在本地实际运行的 Next.js 工作台截图 | 已填写示例需求，未提交模型生成；本地未配置密钥时生成按钮为灰色 |
| continuity-review.png | 实际 ContinuityReview 组件加载演示响应的截图 | 报告、问题和建议均为演示数据，不是一次真实模型调用的结果 |

截图中的商品、需求和问题都是用于介绍功能的虚构示例，没有用户规模、投放收益或模型准确率含义。

截图脚本位于 `scripts/capture-readme.py`。先在 8036 端口运行后端、3036 端口运行前端，再从 backend 目录运行：

```bash
uv run python ../scripts/capture-readme.py
```

脚本使用独立的无头 Chrome 会话，只访问本地服务；审查示例通过浏览器请求替身加载，不创建真实项目、不调用付费模型。需要本机已安装 Chrome 和仓库声明的 Playwright 依赖。
