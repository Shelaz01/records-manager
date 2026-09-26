"""
wia_scan 0.8.0
==========

A simple utility for using document scanners that support Windows Image Acquisition (WIA) and is
easy to install. If your scanner works using Windows Fax and Scan, there is a good chance it will
work with this python script.

See https://github.com/JonasZehn/python_wia_scan for usage and source.

"""

__version__ = "0.8.0"

from .core import *
from .main import *

del tempfile
del sys
del os
del datetime
del docopt
del win32com
del PILImage
