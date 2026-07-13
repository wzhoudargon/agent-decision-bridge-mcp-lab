# Ask First

Use Ask First when the user wants strong external reasoning without opening a
project connector, or when the desired web model does not expose Apps/MCP tools.

## Flow

1. Gather only the facts needed for one decision.
2. Separate confirmed facts, assumptions, constraints, and unknowns.
3. Remove secrets, private data, unnecessary absolute paths, and unrelated
   project content.
4. Create a self-contained Markdown decision package.
5. Ask for recommendation, tradeoffs, risks, concrete steps, and acceptance
   criteria.
6. Send through an actual available advisor channel or hand it to the user.
7. Do not claim consultation until the response returns.
8. Import the response through the review gate.

Ask First is package-only and risk `1/5`. Package readiness is not advisor
completion.

## Compact Chinese Package

```text
# <主题> 决策评审包

## 给外部模型的说明
只基于本文信息判断。不要假设可以访问本地文件、聊天记录或工具。

## 目标
- ...

## 已确认事实
- ...

## 假设与未知
- ...

## 约束与隐私边界
- ...

## 已定决策
- ...

## 待判断问题
1. ...

## 请输出
1. 推荐方案
2. 理由和主要取舍
3. 不建议做什么
4. 缺失信息
5. 给本地执行者的具体步骤
6. 验收标准
7. 主要风险
```

For long web-advisor conversations, prefer a fresh chat with only the current
decision package. Do not paste the whole previous transcript unless archival
context is explicitly required.
