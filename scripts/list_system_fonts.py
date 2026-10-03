from PySide6.QtGui import QFontDatabase, QGuiApplication
app = QGuiApplication([])

families = QFontDatabase.families()
keywords = ['impact', 'anton', 'montserrat', 'poppins', 'arial', 'inter', 'helvetica', 'roboto', 'the bold', 'komika', 'proxima', 'baskerville', 'futura', 'gotham', 'sf pro', 'segoe', 'tiktok', 'bebas']
matches = [f for f in families if any(k in f.lower() for k in keywords)]
print(f"Total system fonts: {len(families)}")
print("Matching popular fonts:")
for f in sorted(set(matches)):
    print(" -", f)
