"""Visual capture of Auto Caption Style Dialog with tabs and CapCut-style templates."""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QEvent
from PySide6.QtGui import QEnterEvent
from kinetic_cut.model import CaptionStyle
from kinetic_cut.caption_style_dialog import CaptionStyleDialog

app = QApplication.instance() or QApplication([])

out_dir = Path("screenshots")
out_dir.mkdir(exist_ok=True)

style = CaptionStyle()
settings = {"caption_words_per_card": 2}
dialog = CaptionStyleDialog(style, settings)
dialog.show()
app.processEvents()

# 1. Grab Caption Setup Tab
dialog.tabs.setCurrentIndex(0)
app.processEvents()
dialog.grab().save(str(out_dir / "caption_dialog_tab_setup.png"))
print("Saved caption_dialog_tab_setup.png")

# 2. Grab Choose Template Tab
dialog.tabs.setCurrentIndex(1)
app.processEvents()
dialog.grab().save(str(out_dir / "caption_dialog_tab_templates.png"))
print("Saved caption_dialog_tab_templates.png")

# 3. Select CapCut Emoji Pop template and grab
emoji_card = next(c for c in dialog.template_cards if c.template.get("id") == "capcut_emoji_pop")
emoji_card.clicked.emit(emoji_card.template)
app.processEvents()
dialog.grab().save(str(out_dir / "caption_dialog_emoji_selected.png"))
print("Saved caption_dialog_emoji_selected.png")

# 4. Trigger card hover and grab
enter_ev = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
emoji_card.enterEvent(enter_ev)
app.processEvents()
dialog.grab().save(str(out_dir / "caption_dialog_card_hover.png"))
print("Saved caption_dialog_card_hover.png")

dialog.close()
