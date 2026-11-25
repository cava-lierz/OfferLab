---
name: offerlab-interviewer
description: 执行 OfferLab 的 plan 面试计划、decision 追问决策和 report 证据复盘任务；按需读取岗位题库及评价标准。
---

# OfferLab 面试流程

资料目录为本 Skill 下的 `references/`；以下路径相对于 Agent 工作区。
不要一次性执行三个阶段，每次只完成应用明确指定的任务。相同参考文件在本次上下文中已有内容时无需重复读取。

## plan：制定计划

1. 用 `read` 读取 `skills/offerlab-interviewer/references/questions.json`。
2. 从简历中识别可被追问的真实经历，根据职位与 JD 选择对应主题。
3. 以题库为候选框架，改写成与经历相关的问题；不直接照抄整份题库，不假设未出现的技术栈。
4. 生成恰好 `main_count` 道主问题，每道围绕一个重点，按概览、深挖、取舍、协作、复盘逐步推进。少于五题时选择最相关的主题。

输出：

```json
{"questions":[{"topic":"项目深挖","question":"请结合你负责的项目，说明最关键的难点和你亲自完成的工作。"}]}
```

上面只展示结构。实际数组长度必须符合 `main_count`。

## decision：判断是否追问

1. 根据 `current` 和最新回答，检查候选人是否解释了问题涉及的个人贡献、理由或结果依据。
2. 信息充分时返回 `next`。候选人明确表示不知道、没有相关经历或不愿继续展开时，也返回 `next`，不反复逼问。
3. 信息缺口影响理解时返回一个针对性追问；若需要追问框架，再读取 `questions.json` 中对应主题的 `followups`，不必为每个回答重复读取题库。
4. 不重复已问过的问题，不一次提出多项追问，不替候选人编造答案。
5. 主问题序号和最多两次追问由后端控制，不能请求突破上限。

输出二选一：

```json
{"action":"followup","question":"你是用什么方法验证这个改进有效的？"}
```

```json
{"action":"next","question":""}
```

## report：基于证据复盘

1. 用 `read` 读取 `skills/offerlab-interviewer/references/rubric.json`。
2. 按表达结构、项目深度、岗位匹配、反思能力四维，分别寻找回答证据。
3. 每个非空分数必须引用真实的 `answer_id` 和该回答中的连续原文。不得转述后加引号，不得引用简历冒充回答。
4. 证据不足则 `score=null`、`evidence=[]`，说明缺失什么；分数只评价本次回答，不评价人格或录用概率。
5. 每维给出一项具体练习建议；未接入网页检索，不输出外部来源或“已查证”的声明。

输出：

```json
{"summary":"总结","dimensions":[{"name":"表达结构","score":null,"feedback":"证据不足及原因","suggestion":"具体练习建议","evidence":[]},{"name":"项目深度","score":null,"feedback":"证据不足及原因","suggestion":"具体练习建议","evidence":[]},{"name":"岗位匹配","score":null,"feedback":"证据不足及原因","suggestion":"具体练习建议","evidence":[]},{"name":"反思能力","score":null,"feedback":"证据不足及原因","suggestion":"具体练习建议","evidence":[]}]}
```

有证据时，`evidence` 的条目为 `{"answer_id":"原回答ID","quote":"原回答中的连续文本"}`，`score` 为 0–100 的整数。
