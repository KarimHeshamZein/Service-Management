"""PostgreSQL connection controls."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..database_core import DatabaseController


class DatabaseTab(ttk.Frame):
    FIELDS = (
        ("host", "PostgreSQL host"),
        ("port", "PostgreSQL port"),
        ("database", "Database name"),
        ("username", "Database user"),
        ("password", "Database password"),
    )

    def __init__(self, parent, controller: DatabaseController) -> None:
        super().__init__(parent, padding=18)
        self.controller = controller
        try:
            current = controller.current()
        except Exception:
            current = {}
        self.values = {
            key: tk.StringVar(value=str(current.get(key) or ""))
            for key, _label in self.FIELDS
        }
        ttk.Label(self, text="PostgreSQL connection", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        for row, (key, label) in enumerate(self.FIELDS, start=1):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(
                self,
                textvariable=self.values[key],
                show="*" if key == "password" else "",
            ).grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Label(
            self,
            text=(
                "Test Connection does not save anything. Save tests first, updates the protected "
                "configuration, restarts the service and rolls back if health checks fail."
            ),
            wraplength=650,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(16, 8))
        buttons = ttk.Frame(self)
        buttons.grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Button(buttons, text="Test Connection", command=self._test).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left")
        self.columnconfigure(1, weight=1)

    def _data(self):
        return {key: value.get() for key, value in self.values.items()}

    def _test(self) -> None:
        result = self.controller.test(self._data())
        if result["ok"]:
            messagebox.showinfo("Database test", result["message"])
        else:
            messagebox.showerror("Database test", "\n".join(result["errors"].values()))

    def _save(self) -> None:
        if not messagebox.askyesno("Save database", "Test and save this production database connection?"):
            return
        try:
            self.controller.save(self._data())
            messagebox.showinfo("Database", "Connection saved and application health verified.")
        except Exception as exc:
            messagebox.showerror("Database", str(exc))
