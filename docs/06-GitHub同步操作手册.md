# 06 GitHub 同步操作手册

## 背景

本机到 `github.com` 的 git 协议不可达（git fetch/push 连接失败）；`api.github.com` 与 `codeload.github.com` 可用，`gh` 命令正常。推送提交用 `gh` 的 Git Data API 完成**快进**（规则见 04 G5；禁 force push 见 G3）。

## 前置条件

- `gh` 已登录目标账号；提交邮箱为 `hlt20051229@gmail.com`（G2）。
- 本地 `main` 的父提交就是远端 `master` 当前头（快进关系）；否则先停下人工核对，不得强行合并。
- 本次 commit 已获用户明确同意（G1）。

## 单提交快进流程

1. 取本地新提交的 tree / message / author / committer；用 `gh api repos/<owner>/<repo>/branches/master` 确认远端头等于本地提交的 parent。
2. 对每个新增/修改的 blob：`gh api repos/<owner>/<repo>/git/blobs` 上传（内容 base64），**断言返回 sha 与本地一致**。
3. `gh api .../git/trees`（`base_tree` = 远端 master 树 + 变动条目；删除的文件以 `sha: null` 列入）创建树。**断言返回的 tree sha 与本地提交树一致**；不一致立即中止，说明两端内容有出入，人工排查，不得强行更新引用。
4. `gh api .../git/commits`（tree、parents=[远端 master 头]、author/committer 与本地一致）创建提交。
5. 本地用 `git hash-object -t commit -w --stdin` 写入与 API 相同的原始提交内容（注意：**GitHub 会去掉提交消息末尾换行**，本地写对象时同样去掉），断言两端 sha 一致；`git update-ref refs/heads/main <sha>`。
6. `gh api .../git/refs/heads/master -X PATCH -f sha=<sha>` 更新 master 引用。
7. 复核：`gh api .../branches/master` 返回的 sha 与本地 main 一致。

## 注意事项

- 全程快进，历史完整保留；过程失败留下的无引用 blob/tree/commit 是无害孤儿对象，无需清理。
- 本地 `ls-tree` 输出对非 ASCII 路径带转义，构造条目时用 `git ls-tree -z` 并按 UTF-8 解码。
- 发布正式版本除本流程外还需：`setup.iss` 版本号与发布号一致、PyInstaller、Inno 编译、`gh release create` 上传安装包（见 04 G4）。
- 需要让 `_release_staging`（安装版目录）与 master 一致时，用 codeload 下载 zip 后全量替换工作目录（保留 .git），不走 git fetch。
