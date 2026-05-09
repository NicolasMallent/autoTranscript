import os
import sys

# Allow imports from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
