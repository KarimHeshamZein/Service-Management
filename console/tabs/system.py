"""Version, backup, diagnostics and verified update controls."""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..system_core import SystemController


class SystemTab(ttk.Frame):
    def __init__(self, parent, controller: SystemController) -> None:
        super().__init__(parent, padding=18)
        self.controller = controller
        ttk.Label(self, text="System information", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )
        self.version = ttk.Label(self)
        self.firewall = ttk.Label(self)
        self.backup = ttk.Label(self, wraplength=650)
        self.version.grid(row=1, column=0, columnspan=3, sticky="w", pady=4)
        self.firewall.grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        self.backup.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(self, text="Refresh", command=self._refresh).grid(row=4, column=0, sticky="w", pady=10)

        self.backup_enabled = tk.BooleanVar()
        self.backup_interval = tk.StringVar()
        self.backup_retention = tk.StringVar()
        self.include_uploads = tk.BooleanVar()
        self.upload_retention = tk.StringVar()
        self.backup_directory = tk.StringVar()
        self.pg_dump_executable = tk.StringVar()
        backup_frame = ttk.LabelFrame(self, text="Automatic backups", padding=12)
        backup_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        backup_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            backup_frame,
            text="Enable scheduled backups",
            variable=self.backup_enabled,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self._field(backup_frame, 1, "Run every (days)", self.backup_interval)
        self._field(backup_frame, 2, "Database backups to retain", self.backup_retention)
        ttk.Checkbutton(
            backup_frame,
            text="Include photo uploads",
            variable=self.include_uploads,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        self._field(backup_frame, 4, "Photo snapshots to retain", self.upload_retention)
        self._path_field(
            backup_frame,
            5,
            "Backup folder",
            self.backup_directory,
            self._choose_backup_directory,
        )
        self._path_field(
            backup_frame,
            6,
            "pg_dump.exe",
            self.pg_dump_executable,
            self._choose_pg_dump,
        )
        ttk.Button(
            backup_frame,
            text="Save and install schedule",
            command=self._save_backup,
        ).grid(row=7, column=0, sticky="w", pady=(10, 0))
        ttk.Button(backup_frame, text="Run Backup Now", command=self._backup).grid(
            row=7, column=1, sticky="w", padx=6, pady=(10, 0)
        )

        ttk.Separator(self).grid(row=6, column=0, columnspan=3, sticky="ew", pady=16)
        ttk.Label(self, text="Application update", font=("Segoe UI", 11, "bold")).grid(
            row=7, column=0, columnspan=3, sticky="w"
        )
        ttk.Button(self, text="Install verified update package", command=self._update).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=8
        )
        ttk.Button(self, text="Export redacted diagnostics", command=self._diagnostics).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=8
        )
        ttk.Button(self, text="Open logs folder", command=self._open_logs).grid(
            row=10, column=0, columnspan=2, sticky="w", pady=8
        )
        self.columnconfigure(2, weight=1)
        self._load_backup_profile()
        self._refresh()

    @staticmethod
    def _field(parent, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable, width=48).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=3
        )

    @staticmethod
    def _path_field(parent, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable, width=48).grid(
            row=row, column=1, sticky="ew", padx=(10, 6), pady=3
        )
        ttk.Button(parent, text="Browse...", command=command).grid(
            row=row, column=2, sticky="e", pady=3
        )

    def _load_backup_profile(self) -> None:
        profile = self.controller.backup_profile()
        self.backup_enabled.set(bool(profile.get("backup_enabled")))
        self.backup_interval.set(str(profile.get("backup_interval_days") or 1))
        self.backup_retention.set(str(profile.get("backup_retention_count") or 30))
        self.include_uploads.set(bool(profile.get("backup_include_uploads")))
        self.upload_retention.set(str(profile.get("backup_upload_retention_count") or 7))
        self.backup_directory.set(str(profile.get("backup_directory") or ""))
        self.pg_dump_executable.set(str(profile.get("pg_dump_executable") or ""))

    def _refresh(self) -> None:
        self.version.configure(text=f"Installed version: {self.controller.version()}")
        self.firewall.configure(text=f"Firewall state: {self.controller.firewall_state()}")
        status = self.controller.backup_status()
        self.backup.configure(text="Backup: " + str(status.get("message") or "Unknown"))

    def _backup(self) -> None:
        self._run(self.controller.run_backup_now, "The backup task was started.")

    def _save_backup(self) -> None:
        values = {
            "backup_enabled": self.backup_enabled.get(),
            "backup_interval_days": self.backup_interval.get(),
            "backup_retention_count": self.backup_retention.get(),
            "backup_include_uploads": self.include_uploads.get(),
            "backup_upload_retention_count": self.upload_retention.get(),
            "backup_directory": self.backup_directory.get(),
            "pg_dump_executable": self.pg_dump_executable.get(),
        }
        self._run(
            lambda: self.controller.configure_backups(values),
            "The backup settings and schedule were updated.",
        )

    def _choose_backup_directory(self) -> None:
        selected = filedialog.askdirectory(title="Select backup folder")
        if selected:
            self.backup_directory.set(selected)

    def _choose_pg_dump(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select pg_dump.exe",
            filetypes=[("PostgreSQL backup tool", "pg_dump.exe"), ("Executables", "*.exe")],
        )
        if selected:
            self.pg_dump_executable.set(selected)

    def _update(self) -> None:
        release = filedialog.askopenfilename(title="Select release ZIP", filetypes=[("ZIP", "*.zip")])
        if not release:
            return
        checksum = filedialog.askopenfilename(
            title="Select SHA-256 file",
            filetypes=[("SHA-256", "*.sha256"), ("Text", "*.txt"), ("All", "*")],
        )
        if not checksum:
            return
        if not messagebox.askyesno("Install update", "Verify and install this release package now?"):
            return
        from pathlib import Path

        self._run(
            lambda: self.controller.install_update(Path(release), Path(checksum)),
            "The verified update was installed.",
        )

    def _diagnostics(self) -> None:
        destination = filedialog.asksaveasfilename(
            title="Export diagnostics",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if destination:
            from pathlib import Path

            self._run(
                lambda: self.controller.export_diagnostics(Path(destination)),
                "Redacted diagnostics exported.",
            )

    def _open_logs(self) -> None:
        os.startfile(self.controller.paths.logs)

    def _run(self, action, success: str) -> None:
        try:
            action()
            messagebox.showinfo("Service Console", success)
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Service Console", str(exc))
