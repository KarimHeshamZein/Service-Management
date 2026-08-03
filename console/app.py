"""Tkinter shell for the local Service Console."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .database_core import DatabaseController
from .network_core import NetworkController
from .paths import InstallPaths
from .service_core import ServiceController
from .system_core import SystemController
from .tabs.database import DatabaseTab
from .tabs.network import NetworkTab
from .tabs.service import ServiceTab
from .tabs.system import SystemTab


class ConsoleApp:
    def __init__(self, paths: InstallPaths) -> None:
        self.root = tk.Tk()
        self.root.title("Afaqy Service Management Console")
        self.root.geometry("920x680")
        self.root.minsize(820, 600)
        service = ServiceController(paths)
        network = NetworkController(paths, service)
        database = DatabaseController(paths, service)
        system = SystemController(paths, service)
        notebook = ttk.Notebook(self.root, padding=8)
        notebook.pack(fill="both", expand=True)
        for label, tab in (
            ("Service", ServiceTab(notebook, service)),
            ("Network", NetworkTab(notebook, network)),
            ("Database", DatabaseTab(notebook, database)),
            ("System", SystemTab(notebook, system)),
        ):
            notebook.add(tab, text=label)

    def run(self) -> None:
        self.root.mainloop()
