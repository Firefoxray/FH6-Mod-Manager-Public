from __future__ import annotations

import filecmp
import os
import subprocess
import sys
from functools import partial
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.backup import (
    list_backups,
    read_backup_display_name,
    read_backup_manifest,
    restore_backup_snapshot,
    update_backup_display_name,
)
from app.mod_manager import (
    ModEntry,
    create_baseline_backup,
    disable_intro_videos,
    find_mod_backup,
    get_uninstallable_new_files,
    install_mod,
    list_mods,
    restore_intro_videos,
    uninstall_mod,
)
from app.paths import APP_ROOT, MODS_ROOT, detect_install_path, normalize_install_path


APP_ICON_PATH = APP_ROOT / "resources" / "icons" / "fh6-mod-manager.png"
RADIO_MOD_WARNING = "Spotify Radio and Universal Radio are alternative radio mods. Install only one at a time."


class MainWindow(QMainWindow):
    PRESETS = (
        (
            "PS4 Wheel + Xbox Controller",
            ("t150_ps4_wheel_xbox_controller", "controller_icons_xbox_stock"),
        ),
        (
            "PS4 Wheel + PS4 Controller",
            ("t150_ps4_wheel_xbox_controller", "controller_icons_ps4"),
        ),
        (
            "PS4 Wheel + PS5 Controller",
            ("t150_ps4_wheel_xbox_controller", "controller_icons_ps5"),
        ),
        (
            "PS5 Wheel + Xbox Controller",
            ("t150_ps5_wheel_xbox_controller", "controller_icons_xbox_stock"),
        ),
        (
            "PS5 Wheel + PS4 Controller",
            ("t150_ps5_wheel_xbox_controller", "controller_icons_ps4"),
        ),
        (
            "PS5 Wheel + PS5 Controller",
            ("t150_ps5_wheel_xbox_controller", "controller_icons_ps5"),
        ),
    )

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FH6 Mod Manager")
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(os.fspath(APP_ICON_PATH)))
        self.resize(1180, 820)

        self.mod_entries: list[ModEntry] = []
        self.backup_entries: list[Path] = []

        self._build_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_install_group())
        main_row = QHBoxLayout()
        main_row.addWidget(self._build_mod_group(), stretch=5)
        main_row.addWidget(self._build_preset_group(), stretch=3)

        layout.addLayout(main_row, stretch=4)
        layout.addWidget(self._build_backup_group(), stretch=2)

        self.refresh_install_path(detect_install_path())
        self.reload_mods()

    def _build_menu_bar(self) -> None:
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About Backups and Safety", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_install_group(self) -> QGroupBox:
        group = QGroupBox("Game Install")
        layout = QGridLayout(group)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select your Forza Horizon 6 install folder")
        self.path_edit.editingFinished.connect(self._on_path_changed)

        detect_button = QPushButton("Auto Detect")
        detect_button.clicked.connect(lambda: self.refresh_install_path(detect_install_path()))

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_install_path)

        open_button = QPushButton("Open Folder")
        open_button.clicked.connect(self._open_install_folder)

        self.status_label = QLabel("Status: Not detected")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        backup_note = QLabel(
            "Current-state backup captures app-managed target files as they are now. It is not a clean "
            "vanilla restore unless your current files are already clean."
        )
        backup_note.setWordWrap(True)

        baseline_button = QPushButton("Create Current-State Backup")
        baseline_button.clicked.connect(self._create_baseline_backup)

        disable_intro_button = QPushButton("Disable Intro Videos")
        disable_intro_button.clicked.connect(self._disable_intro_videos)

        restore_intro_button = QPushButton("Restore Intro Videos")
        restore_intro_button.clicked.connect(self._restore_intro_videos)

        layout.addWidget(QLabel("Install Path"), 0, 0)
        layout.addWidget(self.path_edit, 0, 1, 1, 3)
        layout.addWidget(detect_button, 0, 4)
        layout.addWidget(browse_button, 0, 5)
        layout.addWidget(open_button, 0, 6)
        layout.addWidget(self.status_label, 1, 0, 1, 7)
        layout.addWidget(backup_note, 2, 0, 1, 4)
        layout.addWidget(baseline_button, 2, 4)
        layout.addWidget(disable_intro_button, 2, 5)
        layout.addWidget(restore_intro_button, 2, 6)
        return group

    def _build_mod_group(self) -> QGroupBox:
        group = QGroupBox("Mods")
        layout = QHBoxLayout(group)
        layout.setSpacing(12)

        self.mods_list = QListWidget()
        self.mods_list.currentRowChanged.connect(self._show_selected_mod_details)

        right_panel = QVBoxLayout()
        self.mod_details = QTextEdit()
        self.mod_details.setReadOnly(True)
        self.mod_details.setPlaceholderText(f"No mods found in {MODS_ROOT}")

        install_button = QPushButton("Install Selected Mod")
        install_button.clicked.connect(self._install_selected_mod)

        uninstall_button = QPushButton("Uninstall Selected Mod")
        uninstall_button.clicked.connect(self._uninstall_selected_mod)

        right_panel.addWidget(self.mod_details, stretch=1)
        right_panel.addWidget(install_button)
        right_panel.addWidget(uninstall_button)

        layout.addWidget(self.mods_list, stretch=2)
        layout.addLayout(right_panel, stretch=3)
        return group

    def _build_preset_group(self) -> QGroupBox:
        group = QGroupBox("Wheel + Controller Presets")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        help_text = QLabel("Presets install the wheel UI mod first, then the selected controller icons.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        for label, mod_names in self.PRESETS:
            preset_button = QPushButton(label)
            preset_button.setMinimumHeight(36)
            preset_button.clicked.connect(partial(self._install_preset, label, mod_names))
            layout.addWidget(preset_button)

        layout.addStretch(1)
        return group

    def _build_backup_group(self) -> QGroupBox:
        group = QGroupBox("Backups")
        layout = QVBoxLayout(group)

        self.backups_list = QListWidget()
        self.backups_list.setWordWrap(True)
        self.backups_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        button_row = QHBoxLayout()
        refresh_button = QPushButton("Refresh Backups")
        refresh_button.clicked.connect(self.reload_backups)

        restore_button = QPushButton("Restore Selected Backup")
        restore_button.clicked.connect(self._restore_selected_backup)

        rename_button = QPushButton("Rename Selected Backup")
        rename_button.clicked.connect(self._rename_selected_backup)

        button_row.addWidget(refresh_button)
        button_row.addWidget(restore_button)
        button_row.addWidget(rename_button)

        layout.addWidget(self.backups_list)
        layout.addLayout(button_row)
        return group

    def current_install_path(self) -> Path | None:
        path_text = self.path_edit.text().strip()
        if not path_text:
            return None
        try:
            return normalize_install_path(path_text)
        except OSError:
            return None

    def refresh_install_path(self, install_path: Path | None) -> None:
        if install_path is not None:
            self.path_edit.setText(str(install_path))
        self._update_install_status()
        self.reload_mods()
        self.reload_backups()

    def reload_mods(self) -> None:
        self.mod_entries = list_mods()
        self.mods_list.clear()
        self.mod_details.clear()
        install_path = self.current_install_path()

        for mod in self.mod_entries:
            status, detail = self._mod_install_status(mod, install_path)
            item = QListWidgetItem(f"[{status}] {mod.name}")
            item.setToolTip(detail)
            self.mods_list.addItem(item)

        if self.mod_entries:
            self.mods_list.setCurrentRow(0)
        else:
            self.mod_details.setPlainText(f"No valid mods found in:\n{MODS_ROOT}")

    def reload_backups(self) -> None:
        install_path = self.current_install_path()
        self.backups_list.clear()
        self.backup_entries = []

        if install_path is None or not install_path.is_dir():
            return

        self.backup_entries = list_backups(install_path)
        for snapshot_dir in self.backup_entries:
            label, records = read_backup_manifest(snapshot_dir)
            display_name = read_backup_display_name(snapshot_dir)
            if display_name:
                item_text = (
                    f"{display_name} - {snapshot_dir.name} "
                    f"[{self._display_backup_label(label)}] ({len(records)} tracked paths)"
                )
            else:
                item_text = f"{snapshot_dir.name} [{self._display_backup_label(label)}] ({len(records)} tracked paths)"
            item = QListWidgetItem(item_text)
            item.setToolTip(item_text)
            self.backups_list.addItem(item)

    def _update_install_status(self) -> None:
        install_path = self.current_install_path()
        if install_path is None:
            self.status_label.setText("Status: No install path selected")
            return

        if not install_path.is_dir():
            self.status_label.setText(f"Status: Missing folder at {install_path}")
            return

        media_dir = install_path / "media"
        if media_dir.is_dir():
            self.status_label.setText(f"Status: Ready - install found at {install_path}")
        else:
            self.status_label.setText(
                f"Status: Folder exists, but expected game content is missing at {install_path}"
            )

    def _on_path_changed(self) -> None:
        self._update_install_status()
        self.reload_mods()
        self.reload_backups()

    def _browse_install_path(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(self, "Select Forza Horizon 6 Install Folder")
        if selected_dir:
            self.refresh_install_path(Path(selected_dir))

    def _open_install_folder(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        try:
            subprocess.Popen(["xdg-open", os.fspath(install_path)])
        except OSError as exc:
            self._show_error("Failed to open folder", str(exc))

    def _show_selected_mod_details(self, index: int) -> None:
        if index < 0 or index >= len(self.mod_entries):
            self.mod_details.clear()
            return

        mod = self.mod_entries[index]
        relative_targets = [str(file_path.relative_to(mod.path)) for file_path in mod.install_files]
        install_status, install_status_detail = self._mod_install_status(mod, self.current_install_path())
        details = [
            f"Mod: {mod.name}",
            f"Detected install status: {install_status}",
            install_status_detail,
            f"Source: {mod.path}",
            f"Installs {len(relative_targets)} file(s):",
            *relative_targets[:20],
        ]
        if self._is_radio_mod(mod):
            details.insert(3, RADIO_MOD_WARNING)
        if len(relative_targets) > 20:
            details.append(f"... and {len(relative_targets) - 20} more")
        if mod.readme_path and mod.readme_path.is_file():
            details.append("")
            details.append(mod.readme_path.read_text(encoding="utf-8", errors="replace"))
        self.mod_details.setPlainText("\n".join(details))

    def _require_install_path(self) -> Path | None:
        install_path = self.current_install_path()
        if install_path is None or not install_path.is_dir():
            self._show_error("Install folder missing", "Select a valid Forza Horizon 6 folder first.")
            return None
        return install_path

    def _current_mod(self) -> ModEntry | None:
        index = self.mods_list.currentRow()
        if index < 0 or index >= len(self.mod_entries):
            return None
        return self.mod_entries[index]

    def _create_baseline_backup(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        if not self.mod_entries:
            self._show_error("No mods found", "No mod payloads were found in ./mods to build a backup from.")
            return

        existing_count, backup_dir = create_baseline_backup(install_path, self.mod_entries)
        self.reload_backups()
        QMessageBox.information(
            self,
            "Current-State Backup Created",
            f"Created backup snapshot {backup_dir.name}.\n"
            f"Existing files captured: {existing_count}\n\n"
            "This backs up app-managed target files before changes. It does not restore a clean "
            "Steam/vanilla install unless your current files are already clean.",
        )

    def _install_selected_mod(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        mod = self._current_mod()
        if mod is None:
            self._show_error("No mod selected", "Choose a mod from the list before installing.")
            return

        copied_files, backup_dir = install_mod(install_path, mod)
        self.reload_backups()
        QMessageBox.information(
            self,
            "Mod Installed",
            f"Installed {mod.name}.\nFiles copied: {copied_files}\nBackup: {backup_dir.name}",
        )
        self.reload_mods()

    def _install_preset(self, preset_name: str, mod_names: tuple[str, ...], _checked: bool = False) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        mods_by_name = {mod.name: mod for mod in self.mod_entries}
        missing_names = [name for name in mod_names if name not in mods_by_name]
        if missing_names:
            self._show_error(
                "Preset Mods Missing",
                "This preset cannot be installed because these mod folders were not found:\n"
                + "\n".join(missing_names),
            )
            return

        install_results: list[tuple[str, int, str]] = []
        for mod_name in mod_names:
            copied_files, backup_dir = install_mod(install_path, mods_by_name[mod_name])
            install_results.append((mod_name, copied_files, backup_dir.name))

        self.reload_backups()
        self.reload_mods()

        summary = "\n".join(
            f"{mod_name}: {copied_files} copied file(s), backup {backup_name}"
            for mod_name, copied_files, backup_name in install_results
        )
        QMessageBox.information(
            self,
            "Preset Installed",
            f"Installed {preset_name}.\n\n{summary}",
        )

    def _uninstall_selected_mod(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        mod = self._current_mod()
        if mod is None:
            self._show_error("No mod selected", "Choose a mod from the list before uninstalling.")
            return

        snapshot_dir = find_mod_backup(install_path, mod)
        if snapshot_dir is None:
            self._show_error("No backup found", f"No backup snapshot exists for {mod.name}.")
            return

        removable_files = get_uninstallable_new_files(install_path, mod, snapshot_dir)
        remove_added_files = False
        if removable_files:
            preview = "\n".join(str(path.relative_to(install_path)) for path in removable_files[:12])
            if len(removable_files) > 12:
                preview += f"\n... and {len(removable_files) - 12} more"
            reply = QMessageBox.question(
                self,
                "Remove Added Files?",
                "This uninstall can also remove files that did not exist before the mod was installed.\n\n"
                f"Newest backup: {snapshot_dir.name}\n"
                f"Files that would be deleted:\n{preview}\n\n"
                "Select Yes to remove them, No to keep them, or Cancel to stop.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if reply == QMessageBox.Cancel:
                return
            remove_added_files = reply == QMessageBox.Yes

        restored_files, removed_files, used_snapshot = uninstall_mod(install_path, mod, remove_added_files)
        self.reload_backups()
        QMessageBox.information(
            self,
            "Mod Uninstalled",
            f"Used backup: {used_snapshot.name}\nRestored files: {restored_files}\nRemoved added files: {removed_files}",
        )
        self.reload_mods()

    def _restore_selected_backup(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        index = self.backups_list.currentRow()
        if index < 0 or index >= len(self.backup_entries):
            self._show_error("No backup selected", "Choose a backup snapshot to restore.")
            return

        snapshot_dir = self.backup_entries[index]
        label, records = read_backup_manifest(snapshot_dir)
        display_label = self._display_backup_label(label)
        reply = QMessageBox.question(
            self,
            "Restore Backup?",
            f"Restore tracked files from {snapshot_dir.name}?\n\n"
            f"Type: {display_label}\n"
            f"Tracked paths: {len(records)}\n\n"
            "This overwrites files that existed in the selected backup. It does not delete newer files "
            "that were not part of that backup.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        restored_files = restore_backup_snapshot(install_path, snapshot_dir)
        QMessageBox.information(
            self,
            "Backup Restored",
            f"Restored {restored_files} file(s) from {snapshot_dir.name}.\n"
            f"Type: {display_label}\n"
            f"Tracked paths: {len(records)}\n\n"
            "Restore copies back files that existed in that snapshot. It does not delete newer files "
            "that were not part of the backup.",
        )
        self.reload_mods()

    def _rename_selected_backup(self) -> None:
        index = self.backups_list.currentRow()
        if index < 0 or index >= len(self.backup_entries):
            self._show_error("No backup selected", "Choose a backup snapshot to rename.")
            return

        snapshot_dir = self.backup_entries[index]
        current_name = read_backup_display_name(snapshot_dir)
        new_name, accepted = QInputDialog.getText(
            self,
            "Rename Backup",
            "Friendly display name:",
            text=current_name,
        )
        if not accepted:
            return

        update_backup_display_name(snapshot_dir, new_name)
        self.reload_backups()

    def _disable_intro_videos(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        changed, backup_dir = disable_intro_videos(install_path)
        self.reload_backups()

        if changed == 0:
            QMessageBox.information(
                self,
                "Intro Videos",
                "No intro videos were found, or they are already disabled.",
            )
            return

        backup_text = backup_dir.name if backup_dir is not None else "No backup created"
        QMessageBox.information(
            self,
            "Intro Videos Disabled",
            f"Disabled {changed} intro video(s).\nBackup: {backup_text}",
        )

    def _restore_intro_videos(self) -> None:
        install_path = self._require_install_path()
        if install_path is None:
            return

        changed = restore_intro_videos(install_path)
        if changed == 0:
            QMessageBox.information(self, "Intro Videos", "No disabled intro videos were found.")
            return

        QMessageBox.information(
            self,
            "Intro Videos Restored",
            f"Restored {changed} intro video(s).",
        )

    def _mod_install_status(self, mod: ModEntry, install_path: Path | None) -> tuple[str, str]:
        if install_path is None or not install_path.is_dir():
            return "Unknown", "Select a valid game install folder to check installed files."

        matching_files = 0
        present_files = 0
        total_files = len(mod.install_files)
        for source in mod.install_files:
            target = install_path / source.relative_to(mod.path)
            if not target.is_file():
                continue
            present_files += 1
            if filecmp.cmp(source, target, shallow=False):
                matching_files += 1

        if total_files == 0:
            return "No files", "This mod has no installable payload files."
        if matching_files == total_files:
            return "Installed", "All bundled mod files match the files in the selected install."
        if present_files == 0:
            return "Not installed", "None of this mod's target files were found in the selected install."
        if matching_files == 0:
            return "Different", "Target files exist, but they do not match this bundled mod payload."
        return "Partial", f"{matching_files} of {total_files} bundled file(s) match the selected install."

    def _display_backup_label(self, label: str) -> str:
        if label == "baseline":
            return "current-state backup"
        if label == "intro_videos":
            return "intro videos"
        if label.startswith("mod_"):
            return f"mod install: {label[4:]}"
        return label or "unknown"

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Backups and Safety",
            "FH6 Mod Manager stores backups inside .fh6_mod_manager_backups in the selected game folder.\n\n"
            "Current-state backup means app-managed target files as they exist right now. It does not "
            "mean stock vanilla, and it will not restore a clean Steam install unless the files were "
            "already clean when the backup was made.\n\n"
            "Mod install backups capture the files a mod is about to replace. Uninstall uses the newest "
            "backup for that mod and can optionally remove files that did not exist before install.\n\n"
            f"{RADIO_MOD_WARNING}\n\n"
            "Backup manifests and existing folder names are kept compatible with older FH6 Mod Manager backups.",
        )

    def _is_radio_mod(self, mod: ModEntry) -> bool:
        return mod.name in {"spotify_radio", "universal_radio"}

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
