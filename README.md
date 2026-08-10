# Desktop Toolkit（精简版）

本副本只保留时钟菜单中仍在使用的功能：

- 闹钟、世界时钟和倒计时（含闹铃声音）
- 待办事项和便签
- 区域截图与标注编辑
- 屏幕录像
- 视频播放器（本地文件、在线视频链接和 YouTube；保留 `yt-dlp`）
- 电脑清理
- 开机自启动

已移除文件传输、Google Drive 上传、歌词音乐、番茄钟、自动更新、
语音播报、全屏截图、旧主面板、旧设置面板和悬浮助手。

## 运行

```bat
pip install -r requirements.txt
python main.py
```

快捷键：`Ctrl+Alt+T` 打开时钟界面，`Ctrl+Alt+A` 区域截图。

## 打包

```bat
pip install pyinstaller
python -m PyInstaller --noconfirm DesktopToolkit.spec
```

便携目录为 `dist\SuperTools\`，入口为 `SuperTools.exe`。安装包可用
`ISCC installer\DesktopToolkit.iss` 构建，产物位于 `dist\release\`。

## License

MIT
