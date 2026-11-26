# OfferLab 面试官 Agent 部署

本包针对已检查的学校 OpenClaw `2026.5.22`。它新增或更新独立的 `interviewer`：首次安装使用现有默认模型，更新时保留该 Agent 已显式选择的模型，仅开放 `read` 工具，读取面试 Skill、题库和评价标准。没有安装浏览器、搜索、命令执行或额外插件，也安装器不负责切换模型；个人 DeepSeek 配置见下文。

2026-11-26，开发者已确认个人 DeepSeek 切换成功、响应加快。已完成接入的环境无需重复执行首次配置。

## 源码与安装范围

- `interviewer/`：可提交的工作区源码，包含角色规则、Skill 和参考资料。
- `install_interviewer.py`：增量安装脚本，读取目标机器的现有配置，保留凭据、`main`、插件和 Gateway 设置。
- 项目中的 `openclaw/.openclaw/`：用户复制的完整云端状态，已加入 `.gitignore`。本地准备命令只修改该副本，不表示云端已部署。

Agent 的配置使用 `agents.list`，工作区为 `~/.openclaw/workspace-interviewer`，独立运行目录为 `~/.openclaw/agents/interviewer/agent`。运行状态由 OpenClaw 建立，不复制 `main` 的会话或认证文件。现有全局模型提供商配置继续保留；首次部署到新环境后，仍需通过真实调用确认模型可用。

## 部署到学校

在本机项目根目录打包并上传：

```bash
python3 scripts/package_interviewer.py
scp data/offerlab-interviewer.tar.gz openclaw:~/
ssh openclaw
```

进入学校终端后运行：

```bash
tar -xzf ~/offerlab-interviewer.tar.gz -C ~
python3 ~/offerlab-interviewer/install_interviewer.py --install
```

安装器会：

1. 检查当前配置及实际 OpenClaw 版本。
2. 在临时配置文件上执行 `openclaw config validate`；失败则不修改原配置。
3. 将原配置和已有的本工具管理的面试官工作区备份到 `~/.openclaw/offerlab-backups/时间戳/`。
4. 更新面试官工作区并原子替换配置；写入失败时恢复备份。
5. 输出不含 Token 的安装摘要。不会自动重启 Gateway。

不要把本机复制的整个 `.openclaw` 覆盖回学校。安装包仅含明确列出的源码文件，服务器配置始终以安装时读取的最新文件为基础。

## 验证加载

在学校终端执行：

```bash
openclaw config validate
openclaw agents list
openclaw skills --agent interviewer list
```

确认 Agent 列表中存在 `interviewer`，工作区指向新目录；确认 `offerlab-interviewer` 在该 Agent 的可用 Skill 中。复制文件成功、配置校验通过和模型实际执行 Skill 是三个不同的验收步骤。

若配置命令或工具字段不被该版本接受，保留错误信息以便适配，不要直接删除校验步骤。CLI 若不接受上述 `--agent` 参数位置，先查看 `openclaw skills --help`。

Gateway 是否热加载需按学校运行实例验证。若 CLI 已识别新 Agent 而 HTTP 调用仍未识别，再检查服务加载情况。学校进程由 supervisord 管理，不使用 `systemctl --user`，不为安装文件而直接升级或重建 Gateway。

## 本机应用切换

云端安装并验证后，在本机根目录 `.env` 添加或修改：

```dotenv
OPENCLAW_AGENT_ID=interviewer
```

保留原来的 `OPENCLAW_MODEL=openclaw`、Gateway 地址和 Token。后端通过 `x-openclaw-agent-id: interviewer` 指定目标 Agent，避免把 Agent ID 和模型提供商 ID 混淆。

重启本机应用：

```bash
bash scripts/dev.sh
```

访问 `http://127.0.0.1:8000/api/health` 应看到 `agent_id: interviewer`。新建一场 OpenClaw 面试进行验收。此字段反映后端目标配置，不单独证明云端实际路由正确；仍需结合 Agent 会话或运行记录核对。

首次验收使用虚构示例，检查：

- 计划生成时，真实调用 `read` 读取 Skill 和题库。
- 需要追问时，Agent 根据回答缺口决定继续追问或换题。
- 复盘时，真实读取评价标准，报告引文通过本机后端校验。
- 记录工具调用次数和总耗时。专用 Agent 不等同于模型自动加速，不能把文件存在或模型自称读取过当作调用证据。

`python3 scripts/check_gateway.py` 会携带相同 Agent 目标进行基础连接检查，但不验证完整面试或工具调用轨迹。

## 切回默认 Agent

在本机 `.env` 中清空 `OPENCLAW_AGENT_ID`，重启后端，即恢复原有默认 Agent 路径。现有 `main` 不需要重建。

如果需要恢复服务器配置，应先确认安装后是否还有其他配置变化。备份是完整的历史配置，不能在有后续改动时盲目覆盖。工作区备份和配置备份均位于安装摘要给出的目录。

## 接入个人 DeepSeek API

`scripts/configure_deepseek.py` 在学校端读取最新配置，新增 `personal-deepseek` 提供商和模型白名单，默认仅切换 `interviewer`。个人 API Key 通过终端隐藏输入，保存在学校配置文件中（权限 `600`）；本机 Gateway Token 继续使用原值。

在项目根目录上传脚本，再登录学校运行：

```bash
scp scripts/configure_deepseek.py openclaw:~/configure_deepseek.py
ssh openclaw
python3 ~/configure_deepseek.py --check
python3 ~/configure_deepseek.py
```

脚本默认值为 `https://api.deepseek.com` 和 `deepseek-flash`，不代表当前服务器实际选用的模型。可用 `--model 模型标识` 指定账户支持的模型，或用 `--base-url HTTPS基础地址` 指向自己的兼容服务；请先确认地址再输入对应平台的密钥。需要同时切换默认模型时添加 `--scope defaults-and-interviewer`，其他 Agent 已显式配置的模型不受影响。

脚本先调用学校版本的 `openclaw config validate`，成功后将原配置备份到 `~/.openclaw/offerlab-backups/deepseek-时间戳-随机标识/`，再写入配置。`--check` 使用占位密钥，仅验证配置格式，不验证密钥、网络或模型工具调用。脚本不会重启 Gateway。学校版本为 `2026.5.22`，使用自定义 OpenAI 兼容提供商，无需升级或安装新版插件。

切换后在本机运行 `python3 scripts/check_gateway.py`，并新建面试验证 Skill 读取和输出。若旧会话固定了原模型，应使用新会话；若服务没有热加载，按学校平台的 supervisord 管理方式重载。不要改本机的 `OPENCLAW_MODEL=openclaw`。

密钥输错或需要更换时，重新上传最新脚本，在学校端执行 `python3 ~/configure_deepseek.py --update-key`，隐藏输入正确的密钥。该选项只更新已有提供商的密钥，仍执行配置校验和备份，不更改模型、API 地址或 Agent 设置。校验成功只代表配置格式正确，需再次运行本机 `scripts/check_gateway.py` 验证真实调用。

使用本次更新后的 `install_interviewer.py` 再次安装时，会保留 interviewer 已选择的模型及 fallback 设置；更新工作区前应重新打包上传，旧安装包仍可能覆盖模型选择。已有 `personal-deepseek` 时首次接入模式拒绝覆盖，请使用 `--update-key` 更换密钥，其他设置基于服务器现有配置调整。

## 本地副本准备命令

以下命令仅用于修改本机的云端副本，供查看差异：

```bash
python3 openclaw/install_interviewer.py \
  --prepare-copy openclaw/.openclaw \
  --remote-root /home/idekube/.openclaw
```

此模式不会运行 OpenClaw 校验。写入副本配置的路径仍是学校绝对路径，不应用来在本机启动第二套 OpenClaw。
