"""Windows deep-clean helpers for browser cache, temp files, recycle bin, etc."""

from __future__ import annotations

import os
import shutil
import stat
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class CleanReport:
    bytes_freed: int = 0
    files_removed: int = 0
    folders_touched: int = 0
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def megabytes(self) -> float:
        return self.bytes_freed / (1024 * 1024)

    def summary(self) -> str:
        mb = self.megabytes
        if mb >= 1024:
            size_text = f"{mb / 1024:.2f} GB"
        else:
            size_text = f"{mb:.1f} MB"
        return (
            f"清理完成！释放约 {size_text}，"
            f"处理 {self.files_removed} 个文件"
            + (f"（{len(self.notes)} 项）" if self.notes else "")
            + "。"
        )


_FILE_ATTRIBUTE_REPARSE_POINT = getattr(
    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400
)


def _is_reparse_point(path: Path) -> bool:
    """Return True for symlinks, junctions, mount points and other reparse entries."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attrs = int(getattr(info, "st_file_attributes", 0) or 0)
    return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT) or stat.S_ISLNK(info.st_mode)


def _trusted_local_appdata() -> Path:
    """Resolve LocalAppData without accepting TEMP/TMP as a cleanup authority."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            value = uuid.UUID("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
            folder_id = _GUID(
                value.time_low,
                value.time_mid,
                value.time_hi_version,
                (ctypes.c_ubyte * 8)(*value.bytes[8:]),
            )
            result_path = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(result_path)
            )
            if result == 0 and result_path.value:
                resolved = Path(result_path.value)
                ctypes.windll.ole32.CoTaskMemFree(result_path)
                return resolved
        except Exception:
            pass
    return Path.home() / "AppData" / "Local"


def _trusted_windows_directory() -> Path:
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetWindowsDirectoryW(
                buffer, len(buffer)
            )
            if 0 < length < len(buffer):
                return Path(buffer.value)
        except Exception:
            pass
    return Path(r"C:\Windows")


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _force_writable(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
        return True
    except (OSError, ValueError):
        return False


def _validated_cleanup_root(
    directory: Path, report: CleanReport, label: str
) -> Path | None:
    try:
        absolute = Path(os.path.abspath(directory))
        if not absolute.is_absolute() or not absolute.exists() or not absolute.is_dir():
            return None
        if _is_reparse_point(absolute):
            report.errors.append(f"{label}: 已跳过目录链接")
            return None
        resolved = absolute.resolve(strict=True)
        dangerous = {
            Path(resolved.anchor).resolve(strict=False),
            Path.home().resolve(strict=False),
            Path.cwd().resolve(strict=False),
        }
        if resolved in dangerous:
            report.errors.append(f"{label}: 已拒绝危险的清理根目录")
            return None
        return resolved
    except OSError as exc:
        report.errors.append(f"{label}: {exc}")
        return None


def _remove_path(path: Path, report: CleanReport, root: Path) -> None:
    try:
        os.lstat(path)
    except OSError:
        return
    if _is_reparse_point(path):
        report.errors.append(f"{path.name}: 已跳过目录链接")
        return
    if not _is_within(path, root):
        report.errors.append(f"{path.name}: 已跳过清理根目录外的对象")
        return
    try:
        if path.is_file():
            size = _safe_size(path)
            _force_writable(path)
            path.unlink(missing_ok=True)
            report.bytes_freed += size
            report.files_removed += 1
            return
        if path.is_dir():
            for child in path.iterdir():
                _remove_path(child, report, root)
            try:
                path.rmdir()
            except OSError:
                pass
            report.folders_touched += 1
    except OSError as exc:
        report.errors.append(f"{path.name}: {exc}")


def _clear_directory_contents(directory: Path, report: CleanReport, label: str) -> None:
    root = _validated_cleanup_root(directory, report, label)
    if root is None:
        return
    before = report.bytes_freed
    try:
        for child in root.iterdir():
            # Skip locked system-critical names defensively.
            name = child.name.lower()
            if name in {"desktop.ini", "thumbs.db"} and "temp" not in str(root).lower():
                continue
            _remove_path(child, report, root)
    except OSError as exc:
        report.errors.append(f"{label}: {exc}")
        return
    freed = report.bytes_freed - before
    if freed > 0 or report.files_removed > 0:
        report.notes.append(label)


def _browser_cache_roots() -> list[tuple[str, Path]]:
    local = _trusted_local_appdata()
    roots: list[tuple[str, Path]] = []
    candidates = [
        ("Chrome 缓存", local / "Google" / "Chrome" / "User Data" / "Default" / "Cache"),
        ("Chrome Code Cache", local / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache"),
        ("Edge 缓存", local / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"),
        ("Edge Code Cache", local / "Microsoft" / "Edge" / "User Data" / "Default" / "Code Cache"),
        ("Firefox 缓存", local / "Mozilla" / "Firefox" / "Profiles"),
        ("浏览器 GPUCache", local / "Google" / "Chrome" / "User Data" / "Default" / "GPUCache"),
        ("Edge GPUCache", local / "Microsoft" / "Edge" / "User Data" / "Default" / "GPUCache"),
    ]
    # Also clear nested Firefox cache2 folders.
    for label, path in candidates:
        if label.startswith("Firefox") and path.exists() and not _is_reparse_point(path):
            for profile in path.glob("*"):
                cache2 = profile / "cache2"
                if cache2.exists() and not _is_reparse_point(cache2):
                    roots.append((f"Firefox {profile.name} 缓存", cache2))
            continue
        roots.append((label, path))
    ie = local / "Microsoft" / "Windows" / "INetCache"
    roots.append(("IE/兼容缓存", ie))
    return roots


def _temp_roots() -> list[tuple[str, Path]]:
    local = _trusted_local_appdata()
    windows = _trusted_windows_directory()
    roots = [
        ("用户临时目录", local / "Temp"),
        ("Windows Temp", windows / "Temp"),
    ]
    # Prefetch is optional and sometimes locked; only clear files, not the folder itself.
    prefetch = windows / "Prefetch"
    roots.append(("预读取缓存", prefetch))
    return roots


def empty_recycle_bin(report: CleanReport) -> None:
    try:
        import ctypes
        from ctypes import wintypes

        # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        flags = 0x00000001 | 0x00000002 | 0x00000004
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        if result in (0, -2147418113):  # S_OK or already empty-ish
            report.notes.append("回收站")
        else:
            # Still count as attempted.
            report.notes.append("回收站")
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"回收站: {exc}")


def clean_windows_update_download(report: CleanReport) -> None:
    """Clear Windows Update download cache (safe files only, not the service itself)."""
    root = _trusted_windows_directory() / "SoftwareDistribution" / "Download"
    _clear_directory_contents(root, report, "系统更新下载缓存")


def clean_delivery_optimization(report: CleanReport) -> None:
    root = (
        _trusted_windows_directory()
        / "SoftwareDistribution"
        / "DeliveryOptimization"
    )
    _clear_directory_contents(root, report, "传递优化缓存")


# User-facing scopes for the floating cleaner board (id -> label)
CLEAN_SCOPES: list[tuple[str, str, str]] = [
    ("browser", "浏览器缓存", "Chrome / Edge / Firefox 等缓存与 Code Cache"),
    ("temp", "临时文件", "用户 Temp、Windows Temp"),
    ("prefetch", "预读取缓存", "Windows Prefetch（*.pf）"),
    ("thumbs", "缩略图缓存", "Explorer thumbcache_*.db"),
    ("recycle", "回收站", "清空回收站（不可恢复）"),
    ("wu", "系统更新缓存", "SoftwareDistribution\\Download"),
    ("delivery", "传递优化", "Delivery Optimization 缓存"),
]

# Safe first-run defaults. System caches and the recycle bin require explicit choice.
DEFAULT_SCOPES: list[str] = ["temp", "thumbs"]


def _clean_browser(report: CleanReport) -> None:
    for label, path in _browser_cache_roots():
        if "Profiles" in str(path) and path.name == "Profiles":
            continue
        _clear_directory_contents(path, report, label)


def _clean_temp(report: CleanReport) -> None:
    for label, path in _temp_roots():
        if path.name.lower() == "prefetch":
            continue
        _clear_directory_contents(path, report, label)


def _clean_prefetch(report: CleanReport) -> None:
    path = _trusted_windows_directory() / "Prefetch"
    if not path.exists():
        return
    root = _validated_cleanup_root(path, report, "预读取缓存")
    if root is None:
        return
    before = report.bytes_freed
    try:
        for child in root.glob("*.pf"):
            _remove_path(child, report, root)
    except OSError as exc:
        report.errors.append(f"预读取缓存: {exc}")
        return
    if report.bytes_freed > before:
        report.notes.append("预读取缓存")


def _clean_thumbs(report: CleanReport) -> None:
    thumb = _trusted_local_appdata() / "Microsoft" / "Windows" / "Explorer"
    root = _validated_cleanup_root(thumb, report, "缩略图缓存")
    if root is None:
        return
    before = report.bytes_freed
    for child in root.glob("thumbcache_*.db"):
        _remove_path(child, report, root)
    if report.bytes_freed > before:
        report.notes.append("缩略图缓存")


def run_selective_clean(scopes: list[str] | set[str] | None = None) -> CleanReport:
    """Clean only selected scopes. None uses safe defaults; empty means nothing."""
    report = CleanReport()
    chosen = set(scopes) if scopes is not None else set(DEFAULT_SCOPES)
    if not chosen:
        report.notes.append("未选择任何清理范围")
        return report
    if "browser" in chosen:
        _clean_browser(report)
    if "temp" in chosen:
        _clean_temp(report)
    if "prefetch" in chosen:
        _clean_prefetch(report)
    if "thumbs" in chosen:
        _clean_thumbs(report)
    if "recycle" in chosen:
        empty_recycle_bin(report)
    if "wu" in chosen:
        clean_windows_update_download(report)
    if "delivery" in chosen:
        clean_delivery_optimization(report)
    if not report.notes and report.files_removed == 0 and not report.errors:
        report.notes.append("没有找到可清理的垃圾（或文件正在被占用）")
    return report


def run_deep_clean() -> CleanReport:
    """Run a best-effort deep clean (all scopes). Skips locked files without crashing."""
    return run_selective_clean(DEFAULT_SCOPES)


def run_deep_clean_async(
    on_done: Callable[[CleanReport], None],
    scopes: list[str] | set[str] | None = None,
) -> None:
    def worker() -> None:
        report = run_selective_clean(scopes)
        on_done(report)

    threading.Thread(target=worker, daemon=True).start()
