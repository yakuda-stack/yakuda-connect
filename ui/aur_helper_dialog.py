from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                               QLineEdit, QHBoxLayout, QCheckBox)

from translations import tr

CHOICE_PARU_AUTO = "paru_auto"
CHOICE_PARU_LINK = "paru_link"
CHOICE_CUSTOM = "custom"
CHOICE_FLATPAK = "flatpak"

HINT_PARU = "paru"
HINT_YAY = "yay"
HINT_SHELLY = "shelly"


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


class ShellyHintDialog(QDialog):
    """Update ueber Shelly, aber paru/yay fehlen: empfiehlt einen der beiden."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("shelly_hint_title"))
        self.setMinimumWidth(560)
        self.choice = ""

        lay = QVBoxLayout(self)
        intro = QLabel(tr("shelly_hint_text"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        for key, label in ((HINT_PARU, "shelly_hint_paru"),
                           (HINT_YAY, "shelly_hint_yay")):
            btn = QPushButton(tr(label))
            btn.clicked.connect(lambda checked=False, k=key: self._pick(k))
            lay.addWidget(btn)

        info = QLabel(tr("shelly_hint_self"))
        info.setWordWrap(True)
        lay.addWidget(info)
        for name in (HINT_PARU, HINT_YAY):
            lay.addWidget(self._helper_block(name))

        self.chk_hide = QCheckBox(tr("shelly_hint_dont_show"))
        lay.addWidget(self.chk_hide)

        row = QHBoxLayout()
        btn_shelly = QPushButton(tr("shelly_hint_shelly"))
        btn_shelly.clicked.connect(lambda: self._pick(HINT_SHELLY))
        row.addWidget(btn_shelly)
        btn_cancel = QPushButton(tr("shelly_hint_cancel"))
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)
        lay.addLayout(row)

    @property
    def hide_hint(self):
        return self.chk_hide.isChecked()

    def _helper_block(self, name):
        import appimage_installer as appimg
        repo, aur = appimg.helper_install_commands(name)
        url = appimg.helper_url(name)
        aur_note = tr("shelly_hint_aur_note")
        label = QLabel(
            f'<b>{name}</b> – <a href="{url}">{url}</a>'
            f"<pre>{repo}</pre>{aur_note}<pre>{aur}</pre>")
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setWordWrap(True)
        return label

    def _pick(self, key):
        self.choice = key
        self.accept()
