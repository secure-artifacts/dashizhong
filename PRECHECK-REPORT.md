# Desktop Toolkit 正式发布预检报告

报告日期：2026-08-10  
候选版本：1.0.9  
检查对象：精简版源码、独立便携候选包、GitHub 发布与安全扫描配置

## 总体结论

**本地安全整改和独立构建验证通过，但尚不能声明“正式预检通过”。**

预检网页要求的四项云端证据必须全部来自公开的个人 GitHub 仓库。当前目录没有已连接的 GitHub 仓库，也没有可读取的 GitHub CLI 授权，因此 Attestation、Code Scanning、Secret Scanning 和 Dependabot 尚无仓库侧结果可核验。

## 本地检查结果

| 项目 | 结果 | 证据 |
|---|---|---|
| 默认不开机自启，必须由用户明确同意 | 通过 | 默认状态为关闭；安装器不创建启动项；设置界面可撤销 |
| 清理范围由用户逐项选择并二次确认 | 通过 | 空选择不执行；安全默认仅为临时文件和缩略图；危险范围不默认勾选 |
| 清理目录边界与目录联接防护 | 通过 | 可信系统目录解析、根目录拒绝、包含关系校验、重解析点跳过 |
| 录屏临时文件与 FFmpeg 边界 | 通过 | 仅使用受管理的绝对 FFmpeg 路径；取消录制不生成可预测输出；退出清理 |
| 在线视频与 YouTube 输入边界 | 通过 | 在线能力可关闭；URL、输入数量、队列和播放列表均有硬限制及取消机制 |
| 已删除功能残留 | 通过 | 传输、网盘、歌词、旧面板、更新器、语音等旧业务模块在候选包归档中为 0 |
| 构建工具残留 | 通过 | PyInstaller、setuptools、wheel、altgraph 等开发工具未进入最终候选运行库 |
| 独立运行 | 通过 | 运行进程加载候选包内部 `runtime\\python314.dll`，不再加载旧目录运行库 |
| 自动化测试 | 通过 | 18/18 项安全边界单元测试通过 |
| Qt 集成冒烟测试 | 通过 | 设置、清理对话框和保留模块导入通过；安全默认值与播放列表限制正确 |
| 便携包完整性 | 通过 | 7-Zip 完整性测试 `Everything is Ok`；SHA-256 复算一致 |

## 发布链加固结果

- 所有 GitHub Actions 均固定到 40 位提交 SHA。
- 发布标签不直接插入 PowerShell 源码，改为环境变量传入并严格匹配 `vMAJOR.MINOR.PATCH`。
- `VERSION` 必须和标签一致，否则停止构建。
- 运行依赖和 PyInstaller 使用精确版本；构建仅接受二进制 wheel。
- Windows 构建任务只有只读仓库权限；发布任务单独持有发布、OIDC 和证明权限。
- 每一个上传到 Release 的文件都包含在构建来源证明的 `subject-path` 中。
- 已加入 CodeQL `security-extended` 工作流和 Dependabot 的 pip/GitHub Actions 周期检查。
- 安装器不会在安装阶段启用开机自启动。

## 预检网页四项强制门槛

| 强制门槛 | 当前状态 | 原因/下一步 |
|---|---|---|
| Attestation L2（每个 Release 资产） | 待云端验证 | 推送公开个人仓库并创建 `v1.0.9` 标签后由发布工作流签发 |
| Code Scanning 无 Critical | 待云端验证 | CodeQL 工作流已就绪，必须在 GitHub 完整运行后读取告警结果 |
| Secret Scanning 无 Open Alert | 待云端验证 | 公开仓库创建后启用并检查 Secret Scanning 页面 |
| Dependabot 无 Critical | 待云端验证 | 配置已就绪，必须等待 GitHub 生成依赖图和告警结果 |

因此当前正式预检判定为：**待外部证据，不是失败，也尚不是通过。**

## 最终候选包

- 文件：`offline-release-final5/DesktopToolkit-1.0.9-windows-portable.zip`
- 大小：185,312,616 字节
- SHA-256：`3a2605e1b2ef46b62cafd931a827d7bdd61efd7b46532c43159abeb84b6e9826`
- 解压后入口：`DesktopToolkit-1.0.9-portable/SuperTools.exe`

该本地候选包是独立便携包，不是正式签发的安装器。正式的 Inno Setup 安装器会由 GitHub 发布工作流在受控 Windows 构建机上生成并与便携包一起签发证明。

## 旧版与数据清理结论

- 技术上，新候选包已不依赖旧 `exe.win-amd64-3.14` 目录。
- 由于当前沙箱没有旧目录的写权限，旧目录未被删除。
- 本次构建产生的失败中间目录也因同一删除权限策略未能自动移除，但均已被 `.gitignore` 排除，不会进入正式仓库或 Release。
- 不应删除 `%LOCALAPPDATA%\\DesktopToolkit`，其中是用户的待办、便签、闹钟和设置数据。

## 完成正式预检所需的唯一外部阶段

1. 将本源码目录发布到公开的个人 GitHub 仓库，默认分支使用 `main`。
2. 在仓库 Security 设置中确认 Code Scanning、Secret Scanning 和 Dependabot alerts 可用。
3. 推送与 `VERSION` 一致的 `v1.0.9` 标签。
4. 等待 `CodeQL` 与 `Build, attest, and release` 工作流成功。
5. 在预检页面核验四项均通过后，才将该 GitHub Release 定义为正式版并删除旧发行目录。
