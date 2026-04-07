import tkinter as tk

from spire_painter.ui.helpers import flat_button


class PreviewActions:
    """Crop, Save, Side-by-Side, and Open Folder buttons below the preview panel."""

    def __init__(self, parent, on_crop, on_save, on_open_folder, on_side_by_side=None):
        self._frame = tk.Frame(parent, bg="white")
        self._frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.btn_open_folder = flat_button(self._frame, "Open Output Folder", on_open_folder,
                                           bg="#FFF8E1", active_bg="#FFECB3", fg="#FF8F00")
        self.btn_open_folder.pack(side="bottom", fill="x", pady=(10, 0))

        btn_row = tk.Frame(self._frame, bg="white")
        btn_row.pack(side="bottom", fill="x")
        self.btn_crop = flat_button(btn_row, "Crop", on_crop,
                                    state=tk.DISABLED, bg="#E0F2F1", active_bg="#B2DFDB", fg="#00695C")
        self.btn_crop.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_save = flat_button(btn_row, "Save", on_save,
                                    state=tk.DISABLED, bg="#E8EAF6", active_bg="#C5CAE9", fg="#283593")
        self.btn_save.pack(side="left", fill="x", expand=True, padx=(3, 3))
        self.btn_side_by_side = flat_button(
            btn_row, "Side by Side", on_side_by_side or (lambda: None),
            state=tk.DISABLED, bg="#FBE9E7", active_bg="#FFCCBC", fg="#BF360C")
        self.btn_side_by_side.pack(side="left", fill="x", expand=True, padx=(3, 0))

    def enable(self):
        self.btn_crop.config(state=tk.NORMAL)
        self.btn_save.config(state=tk.NORMAL)
        self.btn_side_by_side.config(state=tk.NORMAL)

    def hide(self):
        self._frame.pack_forget()

    def show(self):
        self._frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
