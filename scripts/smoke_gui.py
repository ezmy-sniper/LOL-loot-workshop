"""Exercise widgets and offline execution without contacting a game client."""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loot_workshop.gui import App

with tempfile.TemporaryDirectory() as directory, \
     patch('loot_workshop.gui.history_directory', return_value=Path(directory)), \
     patch('loot_workshop.gui.messagebox.askyesno', return_value=True), \
     patch('loot_workshop.gui.messagebox.showinfo'), \
     patch('loot_workshop.gui.messagebox.showerror') as errors:
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app.load_demo()
    assert len(app.tree.get_children()) == 7
    assert app.metrics['reroll'].get() == '4'
    app.search.set('腕豪')
    assert len(app.tree.get_children()) == 1
    app.search.set('')
    app.threshold.set('631')
    assert app.plan is None
    assert str(app.execute_button['state']) == 'disabled'
    app.threshold.set('630')
    app.load_demo()
    app.execute()
    deadline = time.monotonic() + 15
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert app.report and app.report['status'] == 'complete', app.report
    assert app.report['blueEssenceGained'] == 12955
    assert len(app.tree.get_children()) == 1
    assert not errors.called
    root.destroy()
print('GUI smoke test passed: search, rule invalidation, confirmation, offline execution, progress, report.')
