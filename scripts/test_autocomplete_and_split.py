"""Automated verification for exact-text caption split and inline word autocomplete."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QKeyEvent
from kinetic_cut.model import Caption, CaptionStyle
from kinetic_cut.captions import split_caption
from kinetic_cut.word_list import get_completion, COMMON_WORDS
from kinetic_cut.emoji import EmojiTextEdit

def test_split_caption():
    print("Testing exact-text caption split...")
    original_text = "I was actually guessing that you would win this match"
    c = Caption("c1", 10.0, 16.0, original_text,
                word_timings=[{"text": w, "start": 10.0 + i * 0.5, "end": 10.4 + i * 0.5} for i, w in enumerate(original_text.split())],
                highlighted_words=[2, 3])
    
    left, right = split_caption(c, 13.0)
    assert left is not None and right is not None
    assert left.text == original_text, f"Left text mismatch: {left.text}"
    assert right.text == original_text, f"Right text mismatch: {right.text}"
    assert left.start == 10.0 and left.end == 13.0
    assert right.start == 13.0 and right.end == 16.0
    assert left.highlighted_words == [2, 3]
    assert right.highlighted_words == [2, 3]
    print("[OK] exact-text caption split passed: both parts retain 100% exact text and metadata")

def test_autocomplete():
    print("Testing inline word autocomplete...")
    app = QApplication.instance() or QApplication([])
    
    # Check word dictionary
    assert get_completion("gues") == "sing", f"Expected 'sing' for 'gues', got '{get_completion('gues')}'"
    assert get_completion("Gues") == "sing", f"Expected 'sing' for 'Gues', got '{get_completion('Gues')}'"
    assert get_completion("someth") == "ing"
    assert get_completion("peop") == "le"
    
    # Check UI widget EmojiTextEdit
    editor = EmojiTextEdit()
    editor.setPlainText("We are gues")
    # Move cursor to end
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor._update_suggestion()
    
    assert editor._suggestion == "sing", f"Expected suggestion 'sing', got '{editor._suggestion}'"
    
    # Press Tab key
    tab_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier)
    editor.keyPressEvent(tab_event)
    
    assert editor.toPlainText() == "We are guessing", f"Expected 'We are guessing', got '{editor.toPlainText()}'"
    assert editor._suggestion == "", "Suggestion should clear after Tab completion"
    
    print("[OK] inline predictive autocomplete passed: detected 'gues' -> suggested 'sing' -> Tab completed to 'guessing'")

if __name__ == "__main__":
    test_split_caption()
    test_autocomplete()
    print("All split and autocomplete tests successfully verified!")
