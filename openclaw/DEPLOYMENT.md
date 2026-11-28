# 学校 OpenClaw 面试官部署说明

我在学校已有的 OpenClaw `2026.5.22` 上为 OfferLab 配置了专用 Agent，ID 为 `interviewer`。独立工作区承载面试官的角色规则、Skill、题库和评分标准，学校的默认 Agent 继续使用自己的工作区。部署验收分别检查学校 CLI 的加载结果、本机后端的路由目标和真实任务的工具调用轨迹。

## 部署包与安装位置

本机项目根目录的打包命令生成 `data/offerlab-interviewer.tar.gz`。安装包按清单收录安装器、本说明和 `interviewer/` 工作区源码。项目里的 `openclaw/.openclaw/` 是供本地比对的状态副本，学校现有的运行配置、凭据和会话由学校实例管理。

**本机打包、上传及登录**

```bash
python3 scripts/manage.py package
scp data/offerlab-interviewer.tar.gz openclaw:~/
ssh openclaw
```

**学校终端解包与安装**

```bash
tar -xzf ~/offerlab-interviewer.tar.gz -C ~
python3 ~/offerlab-interviewer/install_interviewer.py --install
```

首次安装和后续更新使用同一入口。安装器读取服务器现有配置，核对版本，把面试官条目合并进 `agents.list`。首次安装沿用默认模型，更新时沿用面试官已选模型及 fallback。工作区位于 `~/.openclaw/workspace-interviewer`，独立运行目录为 `~/.openclaw/agents/interviewer/agent`。

每次更新先对候选配置执行 `openclaw config validate`。校验通过后，安装器把原配置和已由本工具管理的面试官工作区备份到 `~/.openclaw/offerlab-backups/` 的时间戳目录，再更新工作区并原子替换配置。写入失败时会回滚。安装摘要的 `backup` 字段给出备份位置，`validated_by_openclaw` 记录校验结果。Gateway 的加载情况由后续真实请求确认。

## 学校端加载与搜索配置

学校终端提供三项独立检查。

```bash
openclaw config validate
openclaw agents list
openclaw skills --agent interviewer list
```

配置应通过校验，Agent 列表应包含 `interviewer` 及对应工作区，Skill 列表应包含 `offerlab-interviewer`。字段兼容性以学校版本的校验结果为准，CLI 接受的参数位置可由 `openclaw skills --help` 确认。

专用面试官有三个工具。`read` 读取工作区内的规则与参考资料，`web_search` 在备课时检索公开面经，`web_fetch` 在摘要不足时读取原文。搜索提供商配置在学校 Gateway 上，安装器只配置面试官的工具权限。已有可用提供商时，面试官可直接使用。提供商及搜索密钥通过学校终端的配置命令管理。

```bash
openclaw configure --section web
```

该设置适用于整个 Gateway，提供商的选择取决于学校的出网条件和账号权限。[对应版本的搜索工具文档](https://github.com/openclaw/openclaw/blob/v2026.5.22/docs/tools/web.md)

## 本机应用路由

本机后端从项目根目录的 `.env` 读取 Gateway 地址、Token 和运行模式。专用面试官使用以下配置。

```dotenv
OFFERLAB_MODE=openclaw
OPENCLAW_MODEL=openclaw
OPENCLAW_AGENT_ID=interviewer
```

`OPENCLAW_MODEL` 是兼容接口接受的入口标识。`OPENCLAW_AGENT_ID` 经 `x-openclaw-agent-id` 请求头选择工作区。实际生成回复的模型提供商由学校 Agent 配置决定。本机首次配置 Token 的命令是 `python3 scripts/manage.py gateway-config`，通过终端隐藏输入。SSH 转发由单独终端中的 `python3 scripts/manage.py tunnel` 保持在线。

配置改动在本机后端重启后生效。启动命令在项目根目录执行。

```bash
python3 scripts/manage.py dev
```

本机健康接口的 `agent_id` 字段反映后端配置的目标。连接检查 `python3 scripts/manage.py gateway-check` 会使用同一目标发起一次最小模型请求。对应的学校会话轨迹记录实际执行该请求的 Agent。[本机健康接口](http://127.0.0.1:8000/api/health)

## 工具调用的验收依据

备课验收可以使用虚构简历，以“Java 后端实习 · 技术一面”为目标岗位，在 JD 中提出检索公开面经的备课要求。计划完成后，本机可读取已有运行的脱敏摘要。

```bash
python3 scripts/manage.py runs
```

在对应的 `agent=interviewer`、`task=plan` 记录中，`available_tools` 表示当时可用的工具，`tool_call` 和对应的 `tool_result` 说明实际调用及结果。对于返回结构化列表的提供商，`result_count` 表示工具返回的条数。面试官可以依据搜索摘要出题，也可以通过 `web_fetch` 补读原文。

追问验收关注问题是否对应刚提交的回答。报告验收关注评分标准的读取记录，以及每项评分的引文是否能在对应回答中定位。运行摘要同时保留任务耗时和工具调用情况。搜索失败通常从提供商配置和学校出网条件排查。可用工具列表缺项时，排查范围包括全局策略、沙箱和 Gateway 已加载的配置。CLI 已识别 Agent 而 HTTP 请求仍未路由到它时，可通过学校实例的 supervisord 检查 Gateway 是否已加载新配置。

## 个人 DeepSeek 模型配置

专用面试官安装后可以单独绑定个人 DeepSeek 提供商。个人 API Key 由学校端使用，本机仍用原 Gateway Token 认证。配置脚本随项目提供，需从**本机项目根目录**单独上传。

```bash
scp scripts/configure_deepseek.py openclaw:~/configure_deepseek.py
ssh openclaw
```

**学校终端的配置检查与首次写入**

```bash
python3 ~/configure_deepseek.py --check
python3 ~/configure_deepseek.py
```

`--check` 用占位密钥校验配置格式。正式执行时，终端显示 API 地址、目标模型和切换范围，密钥通过隐藏输入录入。脚本默认值为 `https://api.deepseek.com` 和 `deepseek-flash`。实际选择可由 `--model 模型标识` 和 `--base-url HTTPS基础地址` 指定，检查与正式写入使用相同参数。

脚本新增 `personal-deepseek` 提供商和模型白名单，默认只将 `interviewer` 切换到该模型。`--scope defaults-and-interviewer` 会同时切换默认模型，其他显式指定模型的 Agent 仍按各自配置运行。原配置备份到 `~/.openclaw/offerlab-backups/deepseek-时间戳-随机标识/`，含密钥的配置权限为 `600`。脚本使用该学校版本支持的 OpenAI 兼容接口，服务重载由学校平台管理。

已有提供商只需更换密钥时，学校终端使用独立的更新选项。该操作保留模型、地址和 Agent 选择，并执行配置校验与备份。

```bash
python3 ~/configure_deepseek.py --update-key
```

换模型或换密钥后的验收使用本机 `python3 scripts/manage.py gateway-check` 和新建面试，分别确认基础连通性、实际模型、Skill 读取与报告输出。

## 路由恢复与本机副本

清空本机 `.env` 的 `OPENCLAW_AGENT_ID` 并重启后端，应用即恢复默认 Agent 路由。学校端的配置恢复涉及安装摘要指定的备份。备份保存的是当时的完整配置，恢复范围取决于备份后学校端又做过哪些修改。

本机也可以在已有学校状态副本上生成配置差异。执行位置为本机项目根目录。

```bash
python3 openclaw/install_interviewer.py \
  --prepare-copy openclaw/.openclaw \
  --remote-root /home/idekube/.openclaw
```

该模式只写入本机副本，配置中的绝对路径仍指向学校用户目录。实际配置校验和正式安装由学校实例完成。
