# Clock/Alarm v1.0.10 正式发布预检报告

报告日期：2026-08-10

检查对象：产品全量改名后的源码、构建配置、安装器配置、本地便携候选包和 GitHub 发布流程。

## 当前结论

本地改名、功能安全边界和便携包验证均已通过。`v1.0.10` 尚未推送并完成 GitHub Actions，
因此当前结论是：**本地候选合格，正式发布预检仍待云端四项证据通过。**

已有 `v1.0.9` 的成功结果不能替代新版本的 Attestation 和安全扫描结果。

## 名称与版本统一

| 使用位置 | 新值 |
|---|---|
| 用户界面和 Release 标题 | `Clock/Alarm` |
| Windows 可执行文件、安装包和便携包 | `Clock-Alarm` |
| 注册表、数据目录、环境变量和代码标识 | `ClockAlarm` / `CLOCK_ALARM_*` |
| 候选版本 | `1.0.10` |

源码、文档、构建配置、测试和本地候选包中的旧产品名称扫描结果均为 0。

## 本地验证结果

| 项目 | 结果 | 证据 |
|---|---|---|
| 安全边界单元测试 | 通过 | 18/18 |
| Python 与 Spec 语法 | 通过 | `compileall` 与 `py_compile` 无错误 |
| PowerShell 构建脚本语法 | 通过 | PowerShell AST 解析无错误 |
| C# 独立启动器编译 | 通过 | 生成 `Clock-Alarm.exe` |
| 便携版启动冒烟测试 | 通过 | 启动后持续运行 5 秒，无立即崩溃 |
| ZIP 完整性 | 通过 | 7-Zip 全量测试 `Everything is Ok` |
| 包内旧名称扫描 | 通过 | 文件名 0，文本内容 0 |
| 差异格式检查 | 通过 | `git diff --check` 无错误 |

## 本地候选包

- 文件：`offline-release-clock-alarm-1.0.10/Clock-Alarm-1.0.10-windows-portable.zip`
- 大小：185,292,665 字节
- SHA-256：`ffbbae484e5034938eb0b7b750dab1a11859ae7f65f7945c98d7d5e3064b9128`
- 解压后入口：`Clock-Alarm-1.0.10-portable/Clock-Alarm.exe`

该文件是本地测试候选包，不是 GitHub Actions 签发的正式 Release 资产。

## 保留的安全控制

- 开机自启动默认关闭，只能由用户在设置中明确同意和撤销。
- 安装器只在卸载时清理启动项，不会在安装阶段启用启动项。
- 电脑清理由用户选择范围，并在执行前再次确认；危险范围不默认勾选。
- 目录清理继续拒绝危险根目录、包含关系和目录链接跳转。
- 录屏继续使用受管理的 FFmpeg 路径，并保留取消与退出清理边界。
- 在线视频和 YouTube 能力可关闭，并保留 URL、队列、输入数量和取消限制。
- GitHub Actions 仍固定到完整提交 SHA，运行依赖继续精确锁定版本。

## 正式发布前必须完成

| 强制门槛 | v1.0.10 当前状态 |
|---|---|
| 每个 Release 资产的 SLSA Provenance Attestation | 待发布工作流生成并逐个验证 |
| Code Scanning 无 Critical | 待新提交的 CodeQL 结果 |
| Secret Scanning 无 Open Alert | 待仓库页面/API 复核 |
| Dependabot 无 Critical | 待仓库页面/API 复核 |

完成方法：提交并推送当前改动，创建与 `VERSION` 一致的 `v1.0.10` 标签，等待
`Build, attest, and release` 与 CodeQL 成功，然后对四个 Release 资产逐个执行 Attestation 验证。

## 数据和历史制品

- 工作区测试数据已从旧目录原样迁移到 `ClockAlarmData`，未删除待办、便签、闹钟或设置。
- 本地旧构建、旧便携包和缓存已移到系统临时隔离目录，没有混入新候选包。
- GitHub 上已经发布的 `v1.0.9` 应作为历史版本保留，不应改名或覆盖。
