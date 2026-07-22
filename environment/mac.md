# Mac 开发环境记录

- 生成日期：2026-07-13
- 最后核对日期：2026-07-22（Asia/Shanghai）
- macOS ProductVersion：15.5
- macOS BuildVersion：24F74
- CPU 架构：arm64
- 原系统 PATH 中的 `python3`：3.14.6（`/opt/homebrew/bin/python3`）
- 旧 bootstrap 项目 Python：3.12.13（其 `.venv` 仅保留在备份目录，未迁移）
- uv：0.11.11
- Git：2.39.5（Apple Git-154）
- Codex CLI：0.144.1
- Conda：26.3.2，检查时未激活，`auto_activate_base` 为 false
- 当前项目绝对路径：`/Users/lei/Desktop/NanoServeLab`

> 该 Mac 环境用于代码开发、轻量测试、数据分析和文档，不用于 nano-vLLM CUDA 正式性能结论。当前未在仓库根目录运行 `uv sync`，也未安装 nano-vLLM 的 CUDA 依赖。

## GitHub 连接

- 2026-07-22 排查发现 `~/.gitconfig` 残留 `http.proxy` / `https.proxy = http://127.0.0.1:7897`，但本机该端口没有代理服务监听；Git 与 `gh` 因此无法访问 GitHub，`gh auth status` 还会把网络失败误报为 token 无效。
- 已删除这两条失效的全局 Git 代理配置。只有在确认本机代理重新监听对应端口时才应恢复；不要把临时代理地址长期写入全局 Git 配置。
- 清除代理后，`git ls-remote origin HEAD`、`gh auth status` 与 `gh api user` 均成功；`gh` 登录账号为 `NEVER-AGAIN-RAY`，原 token 无需重建。
- Codex GitHub 连接器的 OAuth 身份原本是 `NEVER-AGAIN-RAY`，但 GitHub App 只安装在另一账号 `consid-yan`，所以连接器访问私有仓库 `NEVER-AGAIN-RAY/NanoServeLab` 时按权限规则返回 404。
- 已将 `ChatGPT Codex Connector` 安装到 `NEVER-AGAIN-RAY`，并选择 **Only select repositories → NanoServeLab**，没有授权该账号的全部当前和未来仓库。
- 修复后连接器能够列出 `NEVER-AGAIN-RAY/NanoServeLab`、读取仓库元数据和 [PR #15](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/15)；返回权限包含 admin / maintain / pull / push / triage。Git CLI 与 Codex GitHub 连接器两条链路均已恢复。
