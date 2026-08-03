"""Windows adapter and firewall controls."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..config_store import load_profile
from ..network_core import NetworkController


class NetworkTab(ttk.Frame):
    FIELDS = (
        ("local_ip", "LAN IPv4 address"),
        ("local_prefix_length", "Network prefix"),
        ("local_gateway", "Gateway"),
        ("local_dns_servers", "DNS servers"),
        ("public_ip", "Public IPv4 address"),
        ("allowed_remote_ips", "Permitted public clients"),
        ("internal_port", "Application port"),
    )

    def __init__(self, parent, controller: NetworkController) -> None:
        super().__init__(parent, padding=18)
        self.controller = controller
        profile = load_profile(controller.paths.machine_settings)
        self.values = {key: tk.StringVar(value=str(profile.get(key) or "")) for key, _ in self.FIELDS}
        self.adapter = tk.StringVar(value=str(profile.get("local_interface") or ""))
        self.fixed = tk.BooleanVar(value=bool(profile.get("configure_static_local_ip")))
        self.public = tk.BooleanVar(value=bool(profile.get("public_enabled")))
        ttk.Label(self, text="Network and firewall", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(self, text="Adapter").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(self, textvariable=self.adapter, values=controller.adapters()).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(self, text="Use a fixed LAN address", variable=self.fixed).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Checkbutton(self, text="Enable public access", variable=self.public).grid(row=3, column=1, sticky="w", pady=4)
        for row, (key, label) in enumerate(self.FIELDS, start=4):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(self, textvariable=self.values[key]).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(
            self,
            text="Warning: applying adapter settings can disconnect Remote Desktop. Use physical or console access.",
            foreground="#9b4d00",
            wraplength=650,
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(16, 8))
        buttons = ttk.Frame(self)
        buttons.grid(row=13, column=0, columnspan=2, sticky="w")
        ttk.Button(buttons, text="Test", command=self._test).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Apply", command=self._apply).pack(side="left", padx=6)
        ttk.Button(buttons, text="Rollback", command=self._rollback).pack(side="left", padx=6)
        self.columnconfigure(1, weight=1)

    def _data(self):
        return {
            **{key: value.get() for key, value in self.values.items()},
            "public_port": self.values["internal_port"].get(),
            "local_port": self.values["internal_port"].get(),
            "local_interface": self.adapter.get(),
            "configure_static_local_ip": self.fixed.get(),
            "public_enabled": self.public.get(),
            "tls_enabled": False,
        }

    def _test(self) -> None:
        _, errors = self.controller.test(self._data())
        if errors:
            messagebox.showerror("Network test", "\n".join(errors.values()))
        else:
            messagebox.showinfo("Network test", "The network settings are valid.")

    def _apply(self) -> None:
        if not messagebox.askyesno(
            "Apply network settings",
            "Remote Desktop may disconnect. Continue only with a recovery path available?",
        ):
            return
        try:
            self.controller.apply(self._data())
            messagebox.showinfo("Network settings", "Network settings applied and health checked.")
        except Exception as exc:
            messagebox.showerror("Network settings", str(exc))

    def _rollback(self) -> None:
        if not messagebox.askyesno("Rollback network", "Restore the last saved adapter and endpoint state?"):
            return
        try:
            self.controller.rollback()
            messagebox.showinfo("Network rollback", "Previous network settings restored.")
        except Exception as exc:
            messagebox.showerror("Network rollback", str(exc))
