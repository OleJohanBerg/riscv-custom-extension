import clang.cindex
import logging
import platform

# Set default logging handler to avoid "No handler found" warnings.
try:  # Python 2.7+
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logger = logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
	(name, version, code) = platform.linux_distribution()
except:
	(name, version, code) = ('n/a', 'n/a', 'n/a')

if name == 'Ubuntu':
	clang.cindex.Config.set_library_file('/usr/lib/llvm-4.0/lib/libclang-4.0.so')
elif name == 'CentOS':
	clang.cindex.Config.set_library_file('/usr/lib64/llvm/libclang.so')
