from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                               QLineEdit, QHBoxLayout)

from translations import tr

CHOICE_PARU_AUTO = "paru_auto"
CHOICE_PARU_LINK = "paru_link"
CHOICE_CUSTOM = "custom"
CHOICE_FLATPAK = "flatpak"


class AurHelperDialog(QDialog):
    """Arch ohne yay/paru: vier Wege, wie es weitergeht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("aur_dlg_title"))
        self.setMinimumWidth(520)
        self.choice = ""
        self.custom_name = ""

        lay = QVBoxLayout(self)
        intro = QLabel(tr("aur_dlg_text"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        for key, label in ((CHOICE_PARU_AUTO, "aur_dlg_opt1"),
                           (CHOICE_PARU_LINK, "aur_dlg_opt2")):
            btn = QPushButton(tr(label))
            btn.clicked.connect(lambda checked=False, k=key: self._pick(k))
            lay.addWidget(btn)

        info = QLabel(tr("aur_dlg_opt3_info"))
        info.setWordWrap(True)
        lay.addWidget(info)
        row = QHBoxLayout()
        self.edit_custom = QLineEdit()
        self.edit_custom.setPlaceholderText(tr("aur_dlg_opt3_placeholder"))
        row.addWidget(self.edit_custom, 1)
        btn_custom = QPushButton(tr("aur_dlg_opt3"))
        btn_custom.clicked.connect(self._pick_custom)
        row.addWidget(btn_custom)
        lay.addLayout(row)
        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        lay.addWidget(self.lbl_error)

        btn_flatpak = QPushButton(tr("aur_dlg_opt4"))
        btn_flatpak.clicked.connect(lambda: self._pick(CHOICE_FLATPAK))
        lay.addWidget(btn_flatpak)

        btn_close = QPushButton(tr("aur_dlg_later"))
        btn_close.clicked.connect(self.reject)
        lay.addWidget(btn_close)

    def _pick(self, key):
        self.choice = key
        self.accept()

    def _pick_custom(self):
        import appimage_installer as appimg
        name = self.edit_custom.text().strip()
        if not appimg.valid_helper_name(name):
            self.lbl_error.setText(tr("aur_dlg_opt3_invalid"))
            return
        self.custom_name = name
        self._pick(CHOICE_CUSTOM)
