"""Service lifecycle and port controls."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..service_core import ServiceController


class ServiceTab(ttk.Frame):
    def __init__(self, parent, controller: ServiceController) -> None:
        super().__init__(parent, padding=18)
        self.controller = controller
        self.status_var = tk.StringVar(value="Checking...")
        self.port_var = tk.StringVar(value="8993")
        ttk.Label(self, text="Windows service", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 12)
        )
        ttk.Label(self, text="Status:").grid(row=1, column=0, sticky="w")
        ttk.Label(self, textvariable=self.status_var).grid(row=1, column=1, sticky="w")
        for column, (label, action) in enumerate(
            (("Start", controller.start), ("Stop", controller.stop), ("Restart", controller.restart)),
            start=2,
        ):
            ttk.Button(self, text=label, command=lambda fn=action: self._run(fn)).grid(
                row=1, column=column, padx=4
            )
        ttk.Label(self, text="Application port:").grid(row=2, column=0, sticky="w", pady=(18, 4))
        ttk.Entry(self, textvariable=self.port_var, width=12).grid(row=2, column=1, sticky="w", pady=(18, 4))
        ttk.Button(self, text="Check port", command=self._check_port).grid(row=2, column=2, padx=4, pady=(18, 4))
        ttk.Button(self, text="Apply port", command=self._apply_port).grid(row=2, column=3, padx=4, pady=(18, 4))
        ttk.Button(self, text="Health check", command=self._health).grid(row=3, column=0, pady=8, sticky="w")
        ttk.Button(self, text="Open application", command=controller.open_application).grid(row=3, column=1, pady=8, sticky="w")
        ttk.Label(self, text="Recent service logs", font=("Segoe UI", 11, "bold")).grid(
            row=4, column=0, columnspan=5, sticky="w", pady=(18, 4)
        )
        self.logs = tk.Text(self, height=22, wrap="none")
        self.logs.grid(row=5, column=0, columnspan=5, sticky="nsew")
        ttk.Button(self, text="Refresh logs", command=self._refresh).grid(row=6, column=0, pady=8, sticky="w")
        self.columnconfigure(4, weight=1)
        self.rowconfigure(5, weight=1)
        self._refresh()

    def _run(self, action) -> None:
        try:
            action()
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Service operation", str(exc))

    def _refresh(self) -> None:
        self.status_var.set(self.controller.status())
        try:
            from app.machine_config.env_file import read_env_file

            self.port_var.set(read_env_file(self.controller.paths.env_file).get("APP_PORT", "8993"))
        except Exception:
            pass
        self.logs.delete("1.0", "end")
        self.logs.insert("1.0", self.controller.recent_logs())

    def _port(self) -> int:
        try:
            return int(self.port_var.get())
        except ValueError:
            raise ValueError("Enter a numeric port from 1 to 65535.") from None

    def _check_port(self) -> None:
        try:
            status = self.controller.check_candidate_port(self._port())
            messagebox.showinfo("Port check", status.message if status else "This is the current application port.")
        except Exception as exc:
            messagebox.showerror("Port check", str(exc))

    def _apply_port(self) -> None:
        try:
            self.controller.change_port(self._port())
            messagebox.showinfo("Port change", "The application is healthy on the new port.")
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Port change", str(exc))

    def _health(self) -> None:
        healthy = self.controller.health_check()
        messagebox.showinfo("Health check", "Application is healthy." if healthy else "Application did not respond.")
