"""Verify themed widget states, compact layout and real modal cancellation."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loot_workshop.gui import App
from loot_workshop import dialogs

root = tk.Tk()
root.attributes('-alpha', 0)
app = App(root)
app.load_demo()
root.update()
assert len(root._hextech_images) == 20
assert app.style.lookup('TButton', 'foreground', ('disabled',)) != app.style.lookup('TButton', 'foreground', ('active',))
for width, height in ((1140, 820), (940, 720)):
    root.geometry(f'{width}x{height}')
    root.update()
    y = app.execute_button.winfo_rooty() - root.winfo_rooty() + app.execute_button.winfo_height()
    assert 0 < y < height, (width, height, y)
    assert app.tree.winfo_height() > 35, app.tree.winfo_height()
    print(f'Layout {width}x{height}: controls visible, table height {app.tree.winfo_height()}')

observed = []
def cancel_dialog():
    def walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from walk(child)
    popup = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    popup.attributes('-alpha', 0)
    popup.update_idletasks()
    buttons = [w for w in walk(popup) if isinstance(w, ttk.Button)]
    assert {str(w['text']) for w in buttons} == {'取消', '确认执行'}
    for button in buttons:
        assert button.winfo_rooty() - popup.winfo_rooty() + button.winfo_height() <= popup.winfo_height()
    assert popup.bind('<Return>') == ''
    observed.append(True)
    next(w for w in buttons if str(w['text']) == '取消').invoke()

root.after(100, cancel_dialog)
assert dialogs.askyesno('确认计划', '重随4次，并分解所得\n直接分解7个碎片\n保留1个碎片', parent=root) is False
assert observed
root.destroy()
print('Theme smoke test passed: texture states, compact layout, themed modal and safe cancel.')
