"""Word-level emphasis presentation in the editable Timings table."""
import html
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QTextDocument,QAbstractTextDocumentLayout,QPalette,QColor
from PySide6.QtWidgets import QStyledItemDelegate,QStyleOptionViewItem,QStyle,QApplication

class HighlightDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        data=index.data(Qt.UserRole+1)
        if not data:return super().paint(painter,option,index)
        indices,color=data; opt=QStyleOptionViewItem(option); self.initStyleOption(opt,index); opt.text=''
        style=opt.widget.style() if opt.widget else QApplication.style(); style.drawControl(QStyle.CE_ItemViewItem,opt,painter,opt.widget)
        ink='#101318' if QColor(color).lightnessF()>.5 else '#ffffff'
        doc=QTextDocument(); doc.setDocumentMargin(0); doc.setDefaultFont(option.font)
        doc.setHtml(' '.join('<span style="background-color:'+color+';color:'+ink+';font-weight:bold">'+html.escape(word)+'</span>' if n in indices else html.escape(word) for n,word in enumerate(index.data().split())))
        context=QAbstractTextDocumentLayout.PaintContext(); context.palette.setColor(QPalette.Text,option.palette.color(QPalette.HighlightedText if option.state&QStyle.State_Selected else QPalette.Text))
        painter.save(); painter.setClipRect(option.rect); painter.translate(option.rect.x()+4,option.rect.y()+(option.rect.height()-doc.size().height())/2)
        doc.documentLayout().draw(painter,context); painter.restore()
