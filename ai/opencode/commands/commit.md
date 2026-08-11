---
description: 对当前仓库（含嵌套子仓）按依赖顺序提交并 push 本次变更。
agent: git-commit-pusher
---

请对当前工作区的本次变更执行提交与 push：

1. 先用 git rev-parse --show-toplevel 确认当前入口仓库，递归识别其下所有独立子仓（含 .git 且 toplevel 指向自身），按深度从深到浅排序。
2. 对每个仓库运行 git status --short、git branch --show-current、git status -sb，确认本次要提交的变更范围。
3. 只提交与用户当前任务相关、且用户已确认要提交的变更；发现无关文件（密钥、日志、构建产物、大二进制）时停下报告。
4. 自底向上提交：先子仓 commit+push 成功，再回父仓检查 gitlink 变化。
5. 提交前尽量跑该仓已有测试/lint/构建验证；无法验证时停止并报告。
6. commit message 用中文，subject 格式 <Type>(<scope>): <subject>；遵守仓库 trailer 披露约定。
7. 完成后表格汇总 repo、branch、files、verification、commit、push result。

用户额外要求：$ARGUMENTS
